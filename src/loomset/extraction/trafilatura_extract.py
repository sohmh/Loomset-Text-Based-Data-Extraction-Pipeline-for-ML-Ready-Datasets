from __future__ import annotations

import re
from datetime import datetime, timezone

import trafilatura
from langdetect import detect


def _clean_extracted_text(text: str) -> str:
    """Remove markdown table artifacts and normalize whitespace."""
    lines = text.splitlines()
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip pure markdown table separator rows (e.g. |---|---|)
        if re.match(r'^[|\s\-:]+$', stripped) and '|' in stripped:
            continue
        # Skip lines that are entirely pipe-delimited table cells with no real prose
        if stripped.startswith('|') and stripped.endswith('|'):
            # Keep the line only if it has substantial text content (not just short cell values)
            inner = stripped.strip('|').strip()
            cells = [c.strip() for c in inner.split('|')]
            cell_text = ' '.join(c for c in cells if c)
            if len(cell_text) < 60:
                continue
        clean_lines.append(line)

    # Collapse 3+ consecutive blank lines into 2
    result = re.sub(r'\n{3,}', '\n\n', '\n'.join(clean_lines))
    return result.strip()


def extract_text(raw_html: str | None, url: str | None = None) -> dict[str, str | None]:
    if not raw_html:
        return {"title": None, "text": None, "lang": None}
    # Use XML output to get metadata (title)
    meta = trafilatura.extract_metadata(raw_html)
    page_title = (meta.title if meta and meta.title else None)

    extracted = trafilatura.extract(raw_html, include_formatting=False, include_links=False, include_tables=False)
    if extracted is None:
        return {"title": page_title, "text": None, "lang": None}
    text = _clean_extracted_text(extracted)
    if not text:
        return {"title": page_title, "text": None, "lang": None}
    try:
        lang = detect(text)
    except Exception:
        lang = "en"
    return {"title": page_title, "text": text, "lang": lang or "en"}


def extract_documents(documents: list[dict]) -> list[dict]:
    results = []
    for doc in documents:
        payload = extract_text(doc.get("raw_html"), doc.get("url"))
        doc["title"] = payload["title"]
        doc["text"] = payload["text"]
        doc["lang"] = payload["lang"]
        doc["extracted_at"] = datetime.now(timezone.utc).isoformat()
        doc["status"] = "extracted" if payload["text"] and len(payload["text"]) > 50 else "failed"
        results.append(doc)
    return results
