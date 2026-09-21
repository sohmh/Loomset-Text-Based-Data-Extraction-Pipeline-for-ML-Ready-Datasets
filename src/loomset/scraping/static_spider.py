from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"


def fetch_url_html(url: str, timeout: int = 20) -> tuple[str | None, str | None]:
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        response = requests.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()
        return response.text, response.url
    except Exception:
        return None, None


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def static_scrape_documents(documents: list[dict[str, Any]], min_html_chars: int = 500) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for doc in documents:
        html, final_url = fetch_url_html(doc["url"])
        if html is None or len(html) < min_html_chars:
            doc["status"] = "needs_dynamic"
            results.append(doc)
            continue
        doc["raw_html"] = html
        doc["fetch_method"] = "static"
        doc["fetched_at"] = datetime.now(timezone.utc).isoformat()
        doc["status"] = "fetched"
        results.append(doc)
    return results


def dynamic_fetch_document(doc: dict[str, Any]) -> dict[str, Any]:
    html, _ = fetch_url_html(doc["url"])
    if html and len(html) >= 100:
        doc["raw_html"] = html
        doc["fetch_method"] = "dynamic"
        doc["status"] = "fetched"
    else:
        doc["status"] = "failed"
    return doc
