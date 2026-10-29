from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_BLOCKED_PATTERNS = [
    "attention required! | cloudflare",
    "just a moment...",
    "<title>access denied</title>",
    "please enable javascript",
    "403 forbidden",
    "404 not found",
    "page not found",
    "security check to continue",
]


def is_soft_blocked(html: str) -> bool:
    """Detect common bot-blocking, captcha, or soft-404 placeholder pages."""
    if not html or len(html) < 200:
        return True
    sample = html[:3000].lower()
    return any(p in sample for p in _BLOCKED_PATTERNS)


def fetch_url_html(url: str, timeout: int = 15) -> tuple[str | None, str | None]:
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        response = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        if response.status_code != 200:
            return None, None

        content = response.text
        if is_soft_blocked(content):
            return None, None

        return content, response.url
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
