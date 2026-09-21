from loomset.storage.db import fetch_documents, upsert_document


def test_rediscovered_url_is_one_document_and_preserves_progress(tmp_path):
    db_path = tmp_path / "loomset.db"
    first = {
        "url": "https://Example.com/article/",
        "query": "first query",
        "domain": "example.com",
        "status": "discovered",
    }
    assert upsert_document(db_path, first) is True

    stored = fetch_documents(db_path)[0]
    upsert_document(db_path, {**first, "url": "https://example.com/article", "status": "discovered"})
    assert upsert_document(db_path, {**stored, "status": "fetched", "raw_html": "<html>content</html>"}) is False

    rows = fetch_documents(db_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "fetched"
    assert rows[0]["raw_html"] == "<html>content</html>"