from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests


def fetch_dynamic_html(url: str, timeout: int = 30) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        try:
            response = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 LoomSet/0.1"})
            response.raise_for_status()
            return response.text
        except Exception:
            return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            html = page.content()
            browser.close()
            return html
    except Exception:
        try:
            response = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 LoomSet/0.1"})
            response.raise_for_status()
            return response.text
        except Exception:
            return None


def dynamic_fetch_document(doc: dict[str, Any]) -> dict[str, Any]:
    html = fetch_dynamic_html(doc["url"])
    if html and len(html) >= 100:
        doc["raw_html"] = html
        doc["fetch_method"] = "dynamic"
        doc["fetched_at"] = datetime.now(timezone.utc).isoformat()
        doc["status"] = "fetched"
    else:
        doc["status"] = "failed"
    return doc
