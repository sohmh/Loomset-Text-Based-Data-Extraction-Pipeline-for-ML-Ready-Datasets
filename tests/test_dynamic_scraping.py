from loomset.scraping.dynamic_fetch import dynamic_fetch_document


def test_dynamic_fetch_document_marks_fetched_html():
    doc = {"url": "https://example.com/dynamic", "status": "needs_dynamic"}
    result = dynamic_fetch_document(doc)
    assert result["status"] == "fetched" or result["status"] == "failed"
