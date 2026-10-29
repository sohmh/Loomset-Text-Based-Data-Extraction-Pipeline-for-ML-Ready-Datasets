from loomset.scraping.dynamic_fetch import dynamic_fetch_document


def test_dynamic_fetch_document_marks_fetched_html(monkeypatch):
    class MockResponse:
        status_code = 200
        text = "<html><head><title>Dynamic Content Page</title></head><body><article><p>This is a sufficiently long mock page for testing dynamic fetching in LoomSet.</p></article></body></html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: MockResponse())
    doc = {"url": "https://example.com/dynamic", "status": "needs_dynamic"}
    result = dynamic_fetch_document(doc)
    assert result["status"] == "fetched"
    assert "Dynamic Content Page" in result["raw_html"]
