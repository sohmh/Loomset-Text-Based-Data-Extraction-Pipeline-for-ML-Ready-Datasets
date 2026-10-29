from __future__ import annotations

import csv as _csv
import json
import random
import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from datasets import Dataset


def _canonical_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = hostname
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def _unique_records(records: list[dict]) -> list[dict]:
    unique: list[dict] = []
    seen_urls: set[str] = set()
    for record in records:
        url = _canonical_url(record.get("url", ""))
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        unique.append({**record, "url": url})
    return unique


def assign_stratified_splits(records: list[dict], seed: int = 42) -> list[dict]:
    """Assign reproducible train/validation/test (80/10/10) splits stratified by label."""
    if not records:
        return []

    rng = random.Random(seed)
    by_label: dict[str, list[dict]] = {}
    for r in records:
        lbl = str(r.get("label") or "unlabeled")
        by_label.setdefault(lbl, []).append(r)

    assigned: list[dict] = []
    for lbl, group in by_label.items():
        shuffled = list(group)
        rng.shuffle(shuffled)
        n = len(shuffled)
        if n == 1:
            shuffled[0]["split"] = "train"
        elif n == 2:
            shuffled[0]["split"] = "train"
            shuffled[1]["split"] = "test"
        else:
            n_train = max(1, int(round(n * 0.80)))
            n_val = max(1 if n >= 5 else 0, int(round(n * 0.10)))
            # Ensure at least test set has items if n >= 3
            if n_train + n_val >= n:
                n_train = n - 2
                n_val = 1
            for i, doc in enumerate(shuffled):
                if i < n_train:
                    doc["split"] = "train"
                elif i < n_train + n_val:
                    doc["split"] = "validation"
                else:
                    doc["split"] = "test"
        assigned.extend(shuffled)

    # Sort back by original id or url for determinism
    assigned.sort(key=lambda x: str(x.get("id") or x.get("url") or ""))
    return assigned


def create_passage_chunks(
    records: list[dict],
    chunk_words: int = 350,
    overlap_words: int = 40,
) -> list[dict]:
    """Break long documents into overlapping passages for Transformer context windows & RAG."""
    chunks: list[dict] = []
    for doc in records:
        text = (doc.get("text") or "").strip()
        if not text:
            continue
        words = text.split()
        doc_id = str(doc.get("id") or "")
        parent_split = doc.get("split") or "train"
        label = doc.get("label") or ""
        label_id = doc.get("label_id", 0)

        if len(words) <= chunk_words:
            chunks.append({
                "chunk_id": f"{doc_id}_c0",
                "doc_id": doc_id,
                "chunk_index": 0,
                "text": text,
                "title": doc.get("title") or "",
                "label": label,
                "label_id": label_id,
                "split": parent_split,
                "word_count": len(words),
                "char_count": len(text),
                "token_estimate": int(len(words) * 1.3),
                "url": doc.get("url") or "",
                "domain": doc.get("domain") or "",
            })
            continue

        step = max(1, chunk_words - overlap_words)
        idx = 0
        for start_idx in range(0, len(words), step):
            end_idx = min(len(words), start_idx + chunk_words)
            chunk_slice = words[start_idx:end_idx]
            chunk_text = " ".join(chunk_slice)
            chunks.append({
                "chunk_id": f"{doc_id}_c{idx}",
                "doc_id": doc_id,
                "chunk_index": idx,
                "text": chunk_text,
                "title": doc.get("title") or "",
                "label": label,
                "label_id": label_id,
                "split": parent_split,
                "word_count": len(chunk_slice),
                "char_count": len(chunk_text),
                "token_estimate": int(len(chunk_slice) * 1.3),
                "url": doc.get("url") or "",
                "domain": doc.get("domain") or "",
            })
            idx += 1
            if end_idx >= len(words):
                break

    return chunks


def export_dataset(records: list[dict], export_dir: str | Path) -> tuple[Path, Path, Path, Path]:
    """Export ML-grade document-level and chunk-level datasets in RFC 4180 CSV, JSON, and Parquet."""
    export_path = Path(export_dir)
    export_path.mkdir(parents=True, exist_ok=True)
    records = _unique_records(records)

    # 1. Build Label Taxonomy & Mappings
    unique_labels = sorted({str(r.get("label") or "unlabeled") for r in records})
    if not unique_labels:
        unique_labels = ["unlabeled"]
    label2id = {lbl: i for i, lbl in enumerate(unique_labels)}
    id2label = {i: lbl for i, lbl in enumerate(unique_labels)}

    # 2. Enrich Records with Label IDs, Token Metrics & Stratified Splits
    enriched: list[dict] = []
    for r in records:
        lbl = str(r.get("label") or "unlabeled")
        raw_text = r.get("text") or ""
        words = raw_text.split()
        enriched.append({
            "id": str(r.get("id") or ""),
            "text": raw_text,
            "title": r.get("title") or "",
            "label": lbl,
            "label_id": label2id.get(lbl, 0),
            "confidence": float(r.get("confidence") or 1.0),
            "word_count": len(words),
            "char_count": len(raw_text),
            "token_estimate": int(len(words) * 1.3),
            "quality_score": float(r.get("quality_score") or 1.0),
            "url": r.get("url") or "",
            "domain": r.get("domain") or "",
            "language": r.get("language") or "en",
            "fetched_at": r.get("fetched_at") or "",
            "label_source": r.get("label_source") or "auto",
            "query": r.get("query") or "",
        })

    enriched = assign_stratified_splits(enriched)

    # 3. Document-Level Hugging Face Dataset & Parquet
    fieldnames = [
        "id", "text", "title", "label", "label_id", "confidence", "split",
        "word_count", "char_count", "token_estimate", "quality_score",
        "url", "domain", "language", "fetched_at", "label_source", "query"
    ]
    if enriched:
        dataset = Dataset.from_list(enriched)
    else:
        dataset = Dataset.from_dict({f: [] for f in fieldnames})

    dataset_path = export_path / "dataset.json"
    dataset.to_json(str(dataset_path))

    parquet_path = export_path / "dataset.parquet"
    dataset.to_parquet(str(parquet_path))

    # 4. Document-Level RFC 4180 Multiline CSV (preserving markdown formatting)
    csv_path = export_path / "dataset.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = _csv.DictWriter(fh, fieldnames=fieldnames, quoting=_csv.QUOTE_ALL)
        writer.writeheader()
        for rec in enriched:
            writer.writerow({f: rec.get(f) for f in fieldnames})

    # 5. Chunk-Level Dataset (for sequence classifiers & RAG embeddings)
    chunk_records = create_passage_chunks(enriched)
    chunk_fieldnames = [
        "chunk_id", "doc_id", "chunk_index", "text", "title", "label", "label_id",
        "split", "word_count", "char_count", "token_estimate", "url", "domain"
    ]
    if chunk_records:
        chunk_dataset = Dataset.from_list(chunk_records)
    else:
        chunk_dataset = Dataset.from_dict({f: [] for f in chunk_fieldnames})

    chunk_json_path = export_path / "dataset_chunks.json"
    chunk_dataset.to_json(str(chunk_json_path))

    chunk_parquet_path = export_path / "dataset_chunks.parquet"
    chunk_dataset.to_parquet(str(chunk_parquet_path))

    chunk_csv_path = export_path / "dataset_chunks.csv"
    with chunk_csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = _csv.DictWriter(fh, fieldnames=chunk_fieldnames, quoting=_csv.QUOTE_ALL)
        writer.writeheader()
        for ch in chunk_records:
            writer.writerow({f: ch.get(f) for f in chunk_fieldnames})

    # 6. Generate Hugging Face Dataset Card & Metrics (README.md)
    split_dist: dict[str, int] = {}
    label_dist: dict[str, int] = {}
    total_tokens = 0
    domains: set[str] = set()
    for r in enriched:
        sp = r.get("split", "train")
        split_dist[sp] = split_dist.get(sp, 0) + 1
        lb = r.get("label", "unlabeled")
        label_dist[lb] = label_dist.get(lb, 0) + 1
        total_tokens += r.get("token_estimate", 0)
        dom = r.get("domain", "")
        if dom:
            domains.add(dom)

    label_lines = "\n".join(f"| `{lbl}` | {label2id.get(lbl, 0)} | {cnt} |" for lbl, cnt in sorted(label_dist.items()))
    split_lines = "\n".join(f"| `{sp}` | {cnt} | {round(cnt / max(len(enriched), 1) * 100, 1)}% |" for sp, cnt in sorted(split_dist.items()))
    domain_lines = "\n".join(f"- `{d}`" for d in sorted(domains)[:20]) if domains else "- N/A"

    card_path = export_path / "README.md"
    card_path.write_text(
        f"""---
annotations_creators:
- machine-generated
language_creators:
- found
language:
- en
license: cc-by-4.0
multilinguality:
- monolingual
size_categories:
- {f"n<{len(enriched) + 1}" if len(enriched) < 1000 else "1K<n<10K"}
source_datasets:
- original
task_categories:
- text-classification
task_ids:
- multi-class-classification
---

# LoomSet Dataset: {enriched[0].get('query', 'Curated Dataset') if enriched else 'Dataset'}

This dataset was curated and structured with the **LoomSet ML Pipeline**. It is fully prepared for text classification, language modeling, RAG indexing, and fine-tuning.

## Dataset Summary

- **Total Documents**: {len(enriched)}
- **Total Passages (Chunks)**: {len(chunk_records)}
- **Estimated Total Tokens**: {total_tokens:,}
- **Number of Classes**: {len(unique_labels)}
- **License**: CC-BY-4.0

## Splits Breakdown

| Split | Documents | Percentage |
|---|---|---|
{split_lines}

## Label Taxonomy (`label2id`)

| Label | Label ID | Documents |
|---|---|---|
{label_lines}

## Data Fields

### Document-Level (`dataset.csv`, `dataset.json`, `dataset.parquet`)
- `id` (string): Unique document UUID.
- `text` (string): Cleaned semantic Markdown article content (RFC 4180 multiline quoted).
- `title` (string): Extracted page title.
- `label` (string): Assigned semantic category.
- `label_id` (integer): Categorical integer ID for PyTorch / Scikit-learn / Hugging Face.
- `confidence` (float): Model confidence score (0.0 to 1.0).
- `split` (string): Stratified partition (`train`, `validation`, `test`).
- `word_count` (integer): Word count.
- `char_count` (integer): Character count.
- `token_estimate` (integer): Estimated subword token count.
- `quality_score` (float): Heuristic text quality rating (0.0 to 1.0).
- `url` (string): Canonical source URL.
- `domain` (string): Origin domain.
- `language` (string): ISO language code.
- `fetched_at` (string): ISO 8601 ingestion timestamp.
- `label_source` (string): `auto` (LLM/semantic) or `human` (review).
- `query` (string): Topic search query.

### Passage-Level (`dataset_chunks.csv`, `dataset_chunks.json`, `dataset_chunks.parquet`)
- `chunk_id` (string): Passage identifier (`<doc_id>_c<idx>`).
- `doc_id` (string): Parent document UUID.
- `chunk_index` (integer): Position index in parent document.
- `text` (string): Passage text within standard Transformer token limits (250–500 words).
- `split` (string): Synchronized with parent document split (zero data leakage).

## Source Domains

{domain_lines}

## How to Load in Python

```python
from datasets import load_dataset
import pandas as pd

# 1. Hugging Face Datasets
dataset = load_dataset("parquet", data_files="{export_path / 'dataset.parquet'}")
print(dataset)

# 2. Pandas (Full multiline markdown support)
df = pd.read_csv("{export_path / 'dataset.csv'}")
print(df.groupby(['split', 'label']).size())
```
""",
        encoding="utf-8",
    )

    return dataset_path, csv_path, parquet_path, card_path
