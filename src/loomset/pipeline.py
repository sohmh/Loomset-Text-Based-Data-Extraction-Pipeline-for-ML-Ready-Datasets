from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol
from uuid import uuid4

from loomset.cleaning.dedup import deduplicate_documents
from loomset.cleaning.language_filter import filter_language
from loomset.cleaning.quality_filter import quality_filter
from loomset.config import load_config
from loomset.discovery.ddg_search import discover_documents
from loomset.export.hf_export import export_dataset
from loomset.extraction.trafilatura_extract import extract_documents
from loomset.labeling.label_schema import LabelResult
from loomset.labeling.ollama_client import auto_label_text
from loomset.review.label_studio_export import export_review_batch
from loomset.scraping.dynamic_fetch import dynamic_fetch_document
from loomset.scraping.static_spider import fetch_url_html
from loomset.storage.db import (
    ensure_db,
    fetch_cleaned_text,
    fetch_documents,
    fetch_extracted_text,
    fetch_labels,
    insert_cleaned_text,
    insert_extracted_text,
    insert_label,
    update_status,
    upsert_document,
)


logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("loomset")


ProgressCallback = Callable[[dict[str, Any]], None]


def _noop_progress(event: dict[str, Any]) -> None:
    pass


def _emit(callback: ProgressCallback, stage: str, status: str, **kwargs: Any) -> None:
    event = {"stage": stage, "status": status, "timestamp": datetime.now(timezone.utc).isoformat(), **kwargs}
    callback(event)


def _ensure_directories(data_dir: str | Path, export_dir: str | Path) -> None:
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    Path(export_dir).mkdir(parents=True, exist_ok=True)


def _query_slug(query: str) -> str:
    """Convert a query string to a safe directory name."""
    import re
    slug = re.sub(r"[^a-z0-9]+", "_", query.lower().strip())
    return slug.strip("_")[:50] or "dataset"


def _seed_documents(db_path: str | Path, query: str, documents: list[dict]) -> None:
    for doc in documents:
        content = doc.get("text") or doc.get("title") or ""
        record = {
            "id": str(uuid4()),
            "url": doc["url"],
            "query": query,
            "domain": doc.get("domain") or "",
            "fetch_method": "static",
            "raw_html": f"<html><body><h1>{doc.get('title', '')}</h1><p>{content}</p></body></html>",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "status": "fetched",
        }
        upsert_document(db_path, record)


def status_summary(db_path: str | Path, query: str | None = None) -> dict[str, int]:
    import sqlite3
    try:
        with sqlite3.connect(db_path) as conn:
            if query:
                rows = conn.execute("SELECT status, COUNT(*) AS count FROM documents WHERE LOWER(query) = LOWER(?) GROUP BY status ORDER BY status", (query,)).fetchall()
            else:
                rows = conn.execute("SELECT status, COUNT(*) AS count FROM documents GROUP BY status ORDER BY status").fetchall()
        return {row[0]: row[1] for row in rows}
    except Exception:
        return {}


def stage_discovery(query: str, max_results: int, db_path: str | Path, callback: ProgressCallback = _noop_progress) -> list[dict]:
    _emit(callback, "discovery", "running", message=f"Discovering URLs for '{query}'...")
    discovered = discover_documents(query, max_results=max_results)
    new_documents: list[dict] = []
    for doc in discovered:
        record = {**doc, "fetched_at": None, "status": "discovered"}
        if upsert_document(db_path, record):
            new_documents.append(record)
    _emit(
        callback,
        "discovery",
        "complete",
        count=len(new_documents),
        seen=len(discovered),
        message=f"Found {len(discovered)} URLs, {len(new_documents)} new",
    )
    return new_documents


def stage_scraping(db_path: str | Path, query: str | None = None, min_html_chars: int = 500, dynamic_fallback: bool = True, callback: ProgressCallback = _noop_progress) -> list[dict]:
    discovered_docs = fetch_documents(db_path, status="discovered", query=query)
    _emit(callback, "scraping", "running", count=len(discovered_docs), message=f"Scraping {len(discovered_docs)} URLs...")
    scraped: list[dict] = []
    for i, doc in enumerate(discovered_docs):
        url = doc.get("url")
        raw_html = doc.get("raw_html")

        # 1. If document already has raw_html (e.g. from seed documents in tests)
        if raw_html and len(raw_html) >= 100:
            doc["fetch_method"] = doc.get("fetch_method") or "seed"
            doc["fetched_at"] = datetime.now(timezone.utc).isoformat()
            doc["status"] = "fetched"
            upsert_document(db_path, doc)
            scraped.append(doc)
            _emit(callback, "scraping", "progress", current=i + 1, total=len(discovered_docs), url=url or "")
            continue

        # 2. Real static scraping via HTTP GET
        if url:
            _emit(callback, "scraping", "progress", current=i + 1, total=len(discovered_docs), url=url, method="static")
            html, _ = fetch_url_html(url, timeout=15)
            if html and len(html) >= min_html_chars:
                doc["raw_html"] = html
                doc["fetch_method"] = "static"
                doc["fetched_at"] = datetime.now(timezone.utc).isoformat()
                doc["status"] = "fetched"
                upsert_document(db_path, doc)
                scraped.append(doc)
                continue

        # 3. Dynamic scrape fallback for JavaScript-rendered sites
        if dynamic_fallback and url:
            _emit(callback, "scraping", "progress", current=i + 1, total=len(discovered_docs), url=url, method="dynamic")
            candidate = dynamic_fetch_document(doc)
            if candidate.get("status") == "fetched" and candidate.get("raw_html") and len(candidate["raw_html"]) >= 100:
                upsert_document(db_path, candidate)
                scraped.append(candidate)
                continue

        # 4. If all fetching fails, mark failed
        doc["status"] = "failed"
        upsert_document(db_path, doc)
        scraped.append(doc)

    fetched_count = sum(1 for d in scraped if d.get("status") == "fetched")
    _emit(callback, "scraping", "complete", count=fetched_count, total=len(discovered_docs), message=f"Scraped {fetched_count}/{len(discovered_docs)} pages")
    return scraped


def stage_extraction(db_path: str | Path, query: str | None = None, callback: ProgressCallback = _noop_progress) -> list[dict]:
    fetched_docs = fetch_documents(db_path, status="fetched", query=query)
    _emit(callback, "extraction", "running", count=len(fetched_docs), message=f"Extracting text from {len(fetched_docs)} pages...")
    extracted_docs = extract_documents(fetched_docs)
    results: list[dict] = []
    for doc in extracted_docs:
        if doc.get("status") == "extracted" and doc.get("text"):
            insert_extracted_text(db_path, doc["id"], doc.get("title"), doc.get("text"), doc.get("lang"), doc["extracted_at"])
            update_status(db_path, doc["id"], "extracted")
            results.append(doc)
        else:
            update_status(db_path, doc["id"], "failed")
    _emit(callback, "extraction", "complete", count=len(results), message=f"Extracted {len(results)} documents")
    return results


def stage_cleaning(db_path: str | Path, query: str | None = None, languages: list[str] | None = None, min_text_length: int = 200, callback: ProgressCallback = _noop_progress) -> list[dict]:
    extracted: list[dict] = []
    for doc in fetch_documents(db_path, status="extracted", query=query):
        extracted_rows = fetch_extracted_text(db_path, doc["id"])
        if not extracted_rows:
            continue
        row = extracted_rows[0]
        extracted.append({
            "id": doc["id"],
            "url": doc["url"],
            "query": doc["query"],
            "domain": doc["domain"],
            "text": row.get("text") or "",
            "lang": row.get("lang") or "en",
        })
    _emit(callback, "cleaning", "running", count=len(extracted), message=f"Cleaning {len(extracted)} documents...")

    before = len(extracted)
    deduped = deduplicate_documents(extracted)
    _emit(callback, "cleaning", "progress", op="dedup", kept=len(deduped), removed=before - len(deduped))

    english = filter_language(deduped, languages or ["en"])
    _emit(callback, "cleaning", "progress", op="language", kept=len(english), removed=len(deduped) - len(english))

    cleaned = quality_filter(english, min_text_length=min_text_length)
    _emit(callback, "cleaning", "progress", op="quality", kept=len(cleaned), removed=len(english) - len(cleaned))

    for doc in cleaned:
        insert_cleaned_text(db_path, doc["id"], doc["text"], doc.get("dedup_hash", ""), doc.get("quality_score", 0.0), datetime.now(timezone.utc).isoformat())
        update_status(db_path, doc["id"], "cleaned")

    total_removed = before - len(cleaned)
    _emit(callback, "cleaning", "complete", count=len(cleaned), removed=total_removed, message=f"Kept {len(cleaned)}, removed {total_removed}")
    return cleaned


def stage_labeling(db_path: str | Path, query: str | None = None, labels: list[str] | None = None, base_url: str | None = None, model: str | None = None, callback: ProgressCallback = _noop_progress) -> list[dict]:
    allowed = labels or ["relevant", "irrelevant"]
    labeled: list[dict] = []
    docs_to_label = []
    for doc in fetch_documents(db_path, status="cleaned", query=query):
        cleaned_rows = fetch_cleaned_text(db_path, doc["id"])
        if not cleaned_rows:
            continue
        docs_to_label.append({"id": doc["id"], "url": doc["url"], "query": doc["query"], "domain": doc["domain"], "text": (cleaned_rows[0].get("text") or "")})

    _emit(callback, "labeling", "running", count=len(docs_to_label), message=f"Labeling {len(docs_to_label)} documents...")

    for i, cleaned_record in enumerate(docs_to_label):
        result = auto_label_text(
            cleaned_record["text"],
            cleaned_record["query"],
            allowed_labels=allowed,
            base_url=base_url or "http://localhost:11434",
            model=model or "",
        )
        label = LabelResult(label=result["label"], confidence=result["confidence"])
        labeled.append({**cleaned_record, "label": label.label, "confidence": label.confidence, "label_source": "auto"})
        insert_label(db_path, cleaned_record["id"], label.label, "auto", label.confidence, False, datetime.now(timezone.utc).isoformat())
        update_status(db_path, cleaned_record["id"], "labeled")
        _emit(callback, "labeling", "progress", current=i + 1, total=len(docs_to_label), label=label.label, confidence=label.confidence)

    # Build label distribution
    label_dist: dict[str, int] = {}
    for rec in labeled:
        lbl = rec.get("label", "unknown")
        label_dist[lbl] = label_dist.get(lbl, 0) + 1
    _emit(callback, "labeling", "complete", count=len(labeled), distribution=label_dist, message=f"Labeled {len(labeled)} documents")
    return labeled


def stage_review(db_path: str | Path, output_path: str | Path | None = None, query: str | None = None, callback: ProgressCallback = _noop_progress) -> dict:
    records: list[dict[str, Any]] = []
    for doc in fetch_documents(db_path, query=query):
        if doc.get("status") not in {"labeled", "reviewed"}:
            continue
        cleaned_row = fetch_cleaned_text(db_path, doc["id"])
        label_row = fetch_labels(db_path, doc["id"])
        if not cleaned_row:
            continue
        label = (label_row[0].get("label") if label_row else "relevant")
        record = {
            "id": doc["id"],
            "text": cleaned_row[0].get("text") or "",
            "label": label,
            "url": doc["url"],
            "domain": doc.get("domain") or "",
            "label_source": (label_row[0].get("label_source") if label_row else "auto"),
        }
        records.append(record)

    if output_path is None:
        config = load_config()
        output_path = Path(config.project.data_dir) / "review" / "label_studio_batch.json"
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    export_review_batch(records, target)

    for doc in fetch_documents(db_path, query=query):
        if doc.get("status") == "labeled":
            update_status(db_path, doc["id"], "reviewed")
            label_rows = fetch_labels(db_path, doc["id"])
            if label_rows:
                insert_label(db_path, doc["id"], label_rows[0]["label"], label_rows[0]["label_source"], float(label_rows[0].get("confidence") or 0.0), True, datetime.now(timezone.utc).isoformat())

    _emit(callback, "review", "complete", count=len(records), message=f"Prepared {len(records)} records for review")
    return {"records": records, "output_path": str(target)}


def stage_export(db_path: str | Path, export_dir: str | Path, query: str | None = None, callback: ProgressCallback = _noop_progress) -> dict:
    exported_records = []
    for doc in fetch_documents(db_path, query=query):
        if doc.get("status") not in {"labeled", "reviewed"}:
            continue
        label_row = fetch_labels(db_path, doc["id"])
        cleaned_row = fetch_cleaned_text(db_path, doc["id"])
        if not cleaned_row:
            continue
        exported_records.append(
            {
                "id": doc["id"],
                "text": cleaned_row[0]["text"],
                "label": label_row[0]["label"] if label_row else "relevant",
                "url": doc["url"],
                "domain": doc["domain"],
                "label_source": label_row[0]["label_source"] if label_row else "auto",
                "query": doc.get("query") or "",
            }
        )
    _emit(callback, "export", "running", count=len(exported_records), message=f"Exporting {len(exported_records)} records...")
    dataset_path, csv_path, parquet_path, card_path = export_dataset(exported_records, export_dir)
    _emit(callback, "export", "complete", count=len(exported_records), message=f"Exported {len(exported_records)} records to {export_dir}")
    return {
        "records": exported_records,
        "dataset_path": dataset_path,
        "csv_path": csv_path,
        "parquet_path": parquet_path,
        "card_path": card_path,
    }


def run_pipeline(
    query: str,
    max_results: int = 10,
    db_path: str | Path | None = None,
    export_dir: str | Path | None = None,
    data_dir: str | Path | None = None,
    labels: list[str] | None = None,
    seed_documents: list[dict] | None = None,
    callback: ProgressCallback = _noop_progress,
) -> dict:
    config = load_config()
    if db_path is None:
        db_path = config.project.db_path
    if data_dir is None:
        data_dir = config.project.data_dir
    # Each query gets its own export subdirectory so runs never overwrite each other
    slug = _query_slug(query)
    if export_dir is None:
        export_dir = Path(config.project.export_dir) / slug
    else:
        export_dir = Path(export_dir) / slug
    _ensure_directories(data_dir, export_dir)
    db_path = str(db_path)
    export_dir = str(export_dir)
    ensure_db(db_path)

    _emit(callback, "pipeline", "running", message=f"Starting pipeline for '{query}'")

    logger.info("Stage: discovery")
    if seed_documents:
        _seed_documents(db_path, query, seed_documents)
        _emit(callback, "discovery", "complete", count=len(seed_documents), message=f"Seeded {len(seed_documents)} documents")
    else:
        stage_discovery(query=query, max_results=max_results, db_path=db_path, callback=callback)

    logger.info("Stage: scraping")
    stage_scraping(db_path=db_path, query=query, min_html_chars=config.scraping.min_html_chars, dynamic_fallback=config.scraping.dynamic_fallback, callback=callback)

    logger.info("Stage: extraction")
    stage_extraction(db_path=db_path, query=query, callback=callback)

    logger.info("Stage: cleaning")
    stage_cleaning(db_path=db_path, query=query, languages=config.cleaning.languages, min_text_length=config.cleaning.min_text_length, callback=callback)

    logger.info("Stage: labeling")
    stage_labeling(
        db_path=db_path,
        query=query,
        labels=labels or config.labeling.allowed_labels,
        base_url=config.labeling.ollama_url,
        model=config.labeling.ollama_model,
        callback=callback,
    )

    logger.info("Stage: review")
    stage_review(db_path=db_path, query=query, callback=callback)

    logger.info("Stage: export")
    result = stage_export(db_path=db_path, export_dir=export_dir, query=query, callback=callback)
    logger.info("Exported %s records", len(result["records"]))
    result["query_slug"] = slug

    # Also sync to base export dir so default root files (dataset.csv, dataset.json, etc.)
    # always reflect this seam rather than holding stale data from older runs.
    base_export_dir = Path(config.project.export_dir)
    if base_export_dir.resolve() != Path(export_dir).resolve():
        base_export_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        for fkey in ("dataset_path", "csv_path", "parquet_path", "card_path"):
            src_file = result.get(fkey)
            if src_file and Path(src_file).exists():
                shutil.copy2(src_file, base_export_dir / Path(src_file).name)

    _emit(callback, "pipeline", "complete", count=len(result["records"]), message="Pipeline complete")
    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run LoomSet pipeline")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--export-dir", default=None)
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    run_pipeline(
        query=args.query,
        max_results=args.max_results,
        db_path=args.db_path,
        export_dir=args.export_dir,
        data_dir=args.data_dir,
    )


if __name__ == "__main__":
    main()
