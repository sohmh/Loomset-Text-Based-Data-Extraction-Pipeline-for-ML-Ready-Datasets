from __future__ import annotations

import logging
from collections.abc import Iterable
from urllib.parse import urlparse, urlunparse

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

import requests

logger = logging.getLogger(__name__)

_SOCIAL_HOSTS = {
    "twitter.com", "x.com", "facebook.com", "instagram.com", "linkedin.com",
}
_SEARCH_BACKENDS = ("bing", "brave", "duckduckgo", "google", "mojeek", "yahoo")


def _fetch_wikipedia_urls(query: str, limit: int = 10) -> list[str]:
    """Return full-text Wikipedia matches as a last-resort discovery source."""
    try:
        response = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query", "list": "search", "srsearch": query,
                "srlimit": limit, "srnamespace": 0, "format": "json",
            },
            headers={"User-Agent": "LoomSet/0.1 (dataset pipeline; contact: project maintainers)"},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json().get("query", {}).get("search", [])
        from urllib.parse import quote

        return [
            "https://en.wikipedia.org/wiki/" + quote(item["title"].replace(" ", "_"), safe="()_'-")
            for item in results if isinstance(item, dict) and item.get("title")
        ]
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        logger.warning("Wikipedia discovery failed for %r: %s", query, exc)
        pass
    return []


def _is_content_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        return (
            parsed.scheme.lower() in {"http", "https"}
            and bool(host)
            and not any(host == domain or host.endswith("." + domain) for domain in _SOCIAL_HOSTS)
            and not any(token in host for token in ("login",))
        )
    except ValueError:
        return False


def _ddgs_results(query: str, limit: int, backend: str | None = None) -> list[str]:
    """Query one backend; isolate failures so another provider can still work."""
    try:
        try:
            client = DDGS(timeout=6)
        except TypeError:
            client = DDGS()
        with client as ddgs:
            kwargs = {"max_results": limit}
            if backend:
                kwargs["backend"] = backend
            try:
                items = ddgs.text(query, **kwargs)
            except TypeError:
                # Compatibility with older ddgs versions and simple injected clients.
                if not backend:
                    raise
                items = ddgs.text(query, max_results=limit)
            urls = []
            try:
                for item in items or []:
                    url = item.get("href") or item.get("url")
                    if isinstance(url, str) and _is_content_url(url):
                        urls.append(url)
            except Exception as exc:
                logger.info("Search backend %s returned partial results for %r: %s", backend or "default", query, exc)
            return urls
    except Exception as exc:
        logger.info("Search backend %s failed for %r: %s", backend or "default", query, exc)
        return []


def fetch_urls(query: str, max_results: int = 10) -> list[str]:
    if not query.strip() or max_results <= 0:
        return []

    # Do not let a broken default/auto engine mask every other provider. Query
    # independent backends and preserve successful results if another errors.
    results: list[str] = []
    for backend in _SEARCH_BACKENDS:
        results.extend(_ddgs_results(query, max_results, backend))
        unique = dedupe_urls(results)
        if len(unique) >= max_results:
            return unique[:max_results]

    # Wikipedia is a last-resort fallback rather than a replacement for web search.
    if not results:
        results.extend(_fetch_wikipedia_urls(query, limit=max_results))
    deduped = dedupe_urls(results)
    if not deduped:
        logger.warning("No URLs discovered for %r: all search providers failed or returned no usable results", query)
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
        if not _is_content_url(normalized) or normalized.lower().split("?", 1)[0].endswith(".pdf"):
            continue
        lower = normalized.lower()
        if any(block in lower for block in ["/login", "/about", "/contact", "/privacy"]) or any(
            urlparse(normalized).hostname == host or (urlparse(normalized).hostname or "").endswith("." + host)
            for host in _SOCIAL_HOSTS
        ):
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
