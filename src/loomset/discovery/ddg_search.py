from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlparse, urlunparse

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

import requests


def _fetch_wikipedia_urls(query: str, limit: int = 10) -> list[str]:
    """Free, reliable fallback/supplement search using Wikipedia OpenSearch API."""
    try:
        url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={requests.utils.quote(query)}&limit={limit}&namespace=0&format=json"
        response = requests.get(url, headers={"User-Agent": "LoomSet/0.1 (dataset pipeline)"}, timeout=8)
        if response.status_code == 200:
            data = response.json()
            if len(data) >= 4 and isinstance(data[3], list):
                return [u for u in data[3] if isinstance(u, str) and u.startswith("http")]
    except Exception:
        pass
    return []


def fetch_urls(query: str, max_results: int = 10) -> list[str]:
    results = []
    # 1. Try DuckDuckGo / ddgs
    try:
        with DDGS() as ddgs:
            for item in ddgs.text(query, max_results=max_results):
                url = item.get("href") or item.get("url")
                if not url:
                    continue
                parsed = urlparse(url)
                if not parsed.scheme or not parsed.netloc:
                    continue
                if any(block in parsed.netloc.lower() for block in ["twitter.com", "x.com", "facebook.com", "instagram.com", "linkedin.com", "pdf", "login"]):
                    continue
                results.append(url)
    except Exception:
        results = []

    # 2. If DDGS returned no results, fallback to Wikipedia OpenSearch
    if not results:
        wiki_urls = _fetch_wikipedia_urls(query, limit=max_results)
        for w_url in wiki_urls:
            if w_url not in results:
                results.append(w_url)

    deduped = dedupe_urls(results)
    return deduped[:max_results]


def normalize_url(url: str) -> str:
    """Return the stable URL identity used for discovery and database deduplication."""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = hostname
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def dedupe_urls(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        normalized = normalize_url(url)
        if normalized.endswith(".pdf"):
            continue
        lower = normalized.lower()
        if any(block in lower for block in ["/login", "/about", "/contact", "/privacy", "twitter.com", "x.com", "facebook.com", "linkedin.com"]):
            continue
        if normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def discover_documents(query: str, max_results: int = 10, db_path: str | None = None) -> list[dict]:
    urls = fetch_urls(query, max_results=max_results)
    records = []
    for url in urls:
        records.append(
            {
                "url": url,
                "query": query,
                "domain": urlparse(url).netloc,
                "status": "discovered",
            }
        )
    return records
