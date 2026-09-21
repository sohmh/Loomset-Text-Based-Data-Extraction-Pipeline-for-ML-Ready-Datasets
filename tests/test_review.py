import json
from pathlib import Path

from loomset.pipeline import stage_review
from loomset.review.label_studio_export import export_review_batch
from loomset.storage.db import ensure_db, insert_cleaned_text, insert_label, upsert_document


def test_export_review_batch_writes_label_studio_payload(tmp_path):
    records = [
        {"id": "doc-1", "text": "Solar-punk urban planning reduces emissions.", "label": "relevant", "url": "https://example.com/1"},
        {"id": "doc-2", "text": "Baking sourdough is unrelated.", "label": "irrelevant", "url": "https://example.com/2"},
    ]
    out = tmp_path / "review.json"
    result = export_review_batch(records, out)
    assert result.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload[0]["data"]["label"] == "relevant"
    assert payload[1]["data"]["text"].startswith("Baking")


def test_stage_review_exports_payload_and_marks_documents_reviewed(tmp_path):
    db_path = tmp_path / "review.db"
    ensure_db(db_path)
    upsert_document(
        db_path,
        {
            "id": "doc-1",
            "url": "https://example.com/1",
            "query": "solar-punk",
            "domain": "example.com",
            "fetch_method": "static",
            "raw_html": "<html>ok</html>",
            "fetched_at": "2024-01-01T00:00:00Z",
            "status": "labeled",
        },
    )
    insert_cleaned_text(db_path, "doc-1", "Solar-punk urban planning reduces emissions.", "hash", 0.9, "2024-01-01T00:00:00Z")
    insert_label(db_path, "doc-1", "relevant", "auto", 0.92, False, "2024-01-01T00:00:00Z")

    out_path = tmp_path / "review-output" / "batch.json"
    result = stage_review(db_path=db_path, output_path=out_path)

    assert result["output_path"] == str(out_path)
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload[0]["data"]["label"] == "relevant"
