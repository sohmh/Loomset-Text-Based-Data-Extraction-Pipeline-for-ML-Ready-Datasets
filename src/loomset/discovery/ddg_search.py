from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from urllib.parse import quote, urljoin, urlparse, urlunparse

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

import requests

logger = logging.getLogger(__name__)

_SOCIAL_HOSTS = {
    "twitter.com", "x.com", "facebook.com", "instagram.com", "linkedin.com", "pinterest.com", "reddit.com"
}
_SEARCH_BACKENDS = ("bing", "brave", "duckduckgo", "google", "mojeek", "yahoo")


def _fetch_wikipedia_urls(query: str, limit: int = 10) -> list[str]:
    """Return full-text Wikipedia matches as a discovery source."""
    try:
        response = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query", "list": "search", "srsearch": query,
                "srlimit": limit, "srnamespace": 0, "format": "json",
            },
            headers={"User-Agent": "LoomSet/0.2 (dataset pipeline; contact: maintainers)"},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json().get("query", {}).get("search", [])
        return [
            "https://en.wikipedia.org/wiki/" + quote(item["title"].replace(" ", "_"), safe="()_'-")
            for item in results if isinstance(item, dict) and item.get("title")
        ]
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        logger.warning("Wikipedia discovery failed for %r: %s", query, exc)
    return []


def _is_content_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme.lower() not in {"http", "https"} or not host:
            return False
        if any(host == domain or host.endswith("." + domain) for domain in _SOCIAL_HOSTS):
            return False
        path = parsed.path.lower()
        if any(token in path for token in ("/login", "/signup", "/cart", "/account", "/checkout")):
            return False
        # Ignore media/binary files
        if re.search(r"\.(pdf|png|jpg|jpeg|gif|svg|zip|tar|gz|mp4|mp3|exe)$", path):
            return False
        return True
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


def _expand_topical_links(seed_urls: list[str], query: str, needed: int) -> list[str]:
    """Extract same-domain topical internal links from top seed pages."""
    if needed <= 0 or not seed_urls:
        return []

    tokens = [t.lower() for t in re.findall(r"[a-z0-9]+", query) if len(t) > 2]
    expanded: list[str] = []

    for seed in seed_urls[:3]:
        if len(expanded) >= needed:
            break
        try:
            resp = requests.get(
                seed,
                headers={"User-Agent": "Mozilla/5.0 LoomSet/0.2 (Crawler)"},
                timeout=6,
            )
            if resp.status_code != 200 or not resp.text:
                continue

            parsed_seed = urlparse(seed)
            seed_domain = parsed_seed.netloc.lower()

            # Find anchor links in the page
            raw_hrefs = re.findall(r'href=["\'](.*?)["\']', resp.text, re.IGNORECASE)
            for href in raw_hrefs:
                if href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:"):
                    continue
                full_url = urljoin(seed, href)
                parsed_href = urlparse(full_url)
                if parsed_href.netloc.lower() != seed_domain:
                    continue
                if not _is_content_url(full_url):
                    continue

                # Check if URL path contains topical keywords
                path_lower = parsed_href.path.lower()
                if any(tok in path_lower for tok in tokens):
                    expanded.append(full_url)
                    if len(expanded) >= needed:
                        break
        except Exception:
            continue

    return expanded


def fetch_urls(query: str, max_results: int = 10) -> list[str]:
    if not query.strip() or max_results <= 0:
        return []

    results: list[str] = []
    for backend in _SEARCH_BACKENDS:
        results.extend(_ddgs_results(query, max_results, backend))
        unique = dedupe_urls(results)
        if len(unique) >= max_results:
            return unique[:max_results]

    # Wikipedia search
    if len(dedupe_urls(results)) < max_results:
        results.extend(_fetch_wikipedia_urls(query, limit=max_results))

    # 1-hop in-domain link expansion if we still need more URLs
    deduped = dedupe_urls(results)
    if len(deduped) < max_results and deduped:
        needed = max_results - len(deduped)
        additional = _expand_topical_links(deduped, query, needed=needed)
        results.extend(additional)
        deduped = dedupe_urls(results)

    if not deduped:
        logger.warning("No URLs discovered for %r", query)
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
