from typer.testing import CliRunner

from loomset.cli import app
from loomset.storage.db import ensure_db, insert_cleaned_text, upsert_document

runner = CliRunner()


def test_cli_status_supports_custom_db_path(tmp_path):
    db_path = tmp_path / "status.db"
    ensure_db(db_path)
    upsert_document(
        db_path,
        {
            "id": "doc-1",
            "url": "https://example.com/a",
            "query": "solar-punk",
            "domain": "example.com",
            "fetch_method": "static",
            "raw_html": "<html>demo</html>",
            "fetched_at": "2024-01-01T00:00:00Z",
            "status": "discovered",
        },
    )
    result = runner.invoke(app, ["status", "--db-path", str(db_path)])
    assert result.exit_code == 0
    assert "discovered: 1" in result.stdout


def test_cli_run_stage_labeling_accepts_labels_option(tmp_path):
    db_path = tmp_path / "labeling.db"
    ensure_db(db_path)
    doc_id = "doc-1"
    upsert_document(
        db_path,
        {
            "id": doc_id,
            "url": "https://example.com/a",
            "query": "solar-punk",
            "domain": "example.com",
            "fetch_method": "static",
            "raw_html": "<html>demo</html>",
            "fetched_at": "2024-01-01T00:00:00Z",
            "status": "cleaned",
        },
    )
    insert_cleaned_text(db_path, doc_id, "Solar-punk urban planning creates resilient cities.", "hash", 1.0, "2024-01-01T00:00:00Z")
    result = runner.invoke(app, ["run-stage", "labeling", "--db-path", str(db_path), "--labels", "relevant,irrelevant"])
    assert result.exit_code == 0
    assert "Labeled 1 documents" in result.stdout
