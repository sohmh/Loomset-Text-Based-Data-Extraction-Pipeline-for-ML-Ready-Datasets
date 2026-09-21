from fastapi.testclient import TestClient

from loomset.server import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True


def test_ollama_status_endpoint():
    response = client.get("/api/ollama/status")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "available" in body


def test_api_run_generates_dataset_even_when_discovery_is_empty(tmp_path):
    payload = {
        "query": "solar-punk urban planning",
        "max_results": 2,
        "db_path": str(tmp_path / "loomset.db"),
        "export_dir": str(tmp_path / "exports"),
        "data_dir": str(tmp_path),
        "labels": ["relevant", "irrelevant"],
    }
    response = client.post("/api/run", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["records"] == []
    assert body["dataset_path"].endswith("dataset.json")
    assert body["csv_path"].endswith("dataset.csv")
