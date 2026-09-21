from loomset.discovery.ddg_search import dedupe_urls, fetch_urls


def test_dedupe_urls_removes_duplicates_and_non_content_links():
    urls = [
        "https://example.com/article",
        "https://example.com/article",
        "https://example.com/article.pdf",
        "https://example.com/login",
        "https://example.com/about",
    ]
    result = dedupe_urls(urls)
    assert result == ["https://example.com/article"]


def test_fetch_urls_filters_pdf_and_social_urls(monkeypatch):
    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query, max_results=10):
            return [
                {"href": "https://example.com/article"},
                {"href": "https://example.com/article.pdf"},
                {"href": "https://twitter.com/login"},
            ]

    monkeypatch.setattr("loomset.discovery.ddg_search.DDGS", FakeDDGS)
    assert fetch_urls("solar-punk", max_results=5) == ["https://example.com/article"]
