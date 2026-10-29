from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

import trafilatura
from langdetect import detect


def _clean_extracted_text(text: str) -> str:
    """Normalize extracted text, strip residual table noise and boilerplate."""
    if not text:
        return ""

    # Normalize unicode to NFKC
    text = unicodedata.normalize("NFKC", text)

    lines = text.splitlines()
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            clean_lines.append("")
            continue

        # Skip pure markdown table separator rows (e.g. |---|---|)
        if re.match(r"^[|\s\-:]+$", stripped) and "|" in stripped:
            continue

        # Skip lines that are entirely pipe-delimited table cells with very short content
        if stripped.startswith("|") and stripped.endswith("|"):
            inner = stripped.strip("|").strip()
            cells = [c.strip() for c in inner.split("|")]
            cell_text = " ".join(c for c in cells if c)
            if len(cell_text) < 40:
                continue

        # Skip common web boilerplate artifacts
        lower = stripped.lower()
        if any(lower == b or lower.startswith(b) for b in [
            "cookie policy", "privacy policy", "accept all cookies",
            "manage cookies", "terms of service", "skip to main content",
            "all rights reserved", "subscribe to newsletter", "share this article:"
        ]):
            continue

        clean_lines.append(line)

    # Collapse 3+ consecutive blank lines into 2
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(clean_lines))
    return result.strip()


def extract_text(raw_html: str | None, url: str | None = None) -> dict[str, Any]:
    if not raw_html:
        return {"title": None, "text": None, "lang": None, "description": None, "author": None, "date": None}

    # Extract rich document metadata via Trafilatura
    meta = None
    try:
        meta = trafilatura.extract_metadata(raw_html)
    except Exception:
        pass

    page_title = meta.title if meta and meta.title else None
    description = meta.description if meta and meta.description else None
    author = meta.author if meta and meta.author else None
    date = meta.date if meta and meta.date else None

    # First attempt: semantic Markdown extraction preserving headings and lists
    extracted = None
    try:
        extracted = trafilatura.extract(
            raw_html,
            output_format="markdown",
            include_formatting=True,
            include_links=False,
            include_tables=True,
        )
    except Exception:
        pass

    # Fallback attempt: plain text extraction
    if not extracted:
        try:
            extracted = trafilatura.extract(
                raw_html,
                include_formatting=False,
                include_links=False,
                include_tables=False,
            )
        except Exception:
            pass

    if extracted is None:
        return {
            "title": page_title,
            "text": None,
            "lang": None,
            "description": description,
            "author": author,
            "date": date,
        }

    text = _clean_extracted_text(extracted)
    if not text:
        return {
            "title": page_title,
            "text": None,
            "lang": None,
            "description": description,
            "author": author,
            "date": date,
        }

    try:
        lang = detect(text[:1000])
    except Exception:
        lang = "en"

    return {
        "title": page_title,
        "text": text,
        "lang": lang or "en",
        "description": description,
        "author": author,
        "date": date,
    }


def extract_documents(documents: list[dict]) -> list[dict]:
    results = []
    for doc in documents:
        payload = extract_text(doc.get("raw_html"), doc.get("url"))
        doc["title"] = payload["title"]
        doc["text"] = payload["text"]
        doc["lang"] = payload["lang"]
        doc["description"] = payload.get("description")
        doc["author"] = payload.get("author")
        doc["extracted_at"] = datetime.now(timezone.utc).isoformat()
        doc["status"] = "extracted" if payload["text"] and len(payload["text"]) > 50 else "failed"
        results.append(doc)
    return results
