from __future__ import annotations

from loomset.server import health, ollama_status, api_run, RunRequest


def test_health_endpoint():
    res = health()
    assert res["ok"] is True
    assert res["service"] == "loomset"


def test_ollama_status_endpoint():
    res = ollama_status()
    assert res["ok"] is True
    assert "available" in res
    assert "running" in res


def test_api_run_generates_dataset_even_when_discovery_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("loomset.pipeline.stage_discovery", lambda **kwargs: [])
    req = RunRequest(
        query="solar-punk urban planning",
        max_results=2,
        db_path=str(tmp_path / "loomset.db"),
        export_dir=str(tmp_path / "exports"),
        data_dir=str(tmp_path),
        labels=["relevant", "irrelevant"],
    )
    body = api_run(req)
    assert body["ok"] is True
    assert body["records"] == []
    assert body["dataset_path"].endswith("dataset.json")
    assert body["csv_path"].endswith("dataset.csv")
