from pathlib import Path

from loomset.pipeline import run_pipeline


def test_run_pipeline_generates_dataset(tmp_path):
    query = "solar-punk urban planning"
    result = run_pipeline(
        query=query,
        max_results=2,
        db_path=str(tmp_path / "loomset.db"),
        export_dir=str(tmp_path / "exports"),
        data_dir=str(tmp_path),
        labels=["relevant", "irrelevant"],
        seed_documents=[
            {
                "url": "https://example.com/solar-punk",
                "title": "Solar-Punk Living",
                "text": (
                    "Solar-punk urban planning centers on decentralized, renewable cities with community gardens and resilient public transit. "
                    "This approach emphasizes sustainable architecture, green rooftops, vertical farms, and pedestrian-friendly neighborhoods. "
                    "The movement draws from solarpunk fiction and environmental justice to imagine cities that thrive in harmony with nature."
                ),
                "query": query,
            },
            {
                "url": "https://example.com/other",
                "title": "Cooking Tips",
                "text": (
                    "Learn to bake sourdough bread with a simple starter and a warm kitchen. This article is unrelated to urban planning. "
                    "Sourdough requires patience, good flour, water, and a reliable fermentation schedule. Many bakers keep detailed notes "
                    "on their process, tracking rise times and hydration levels across multiple batches for consistent results."
                ),
                "query": query,
            },
        ],
    )

    assert len(result["records"]) >= 1
    assert result["dataset_path"].exists()
    assert result["csv_path"].exists()
    assert result["parquet_path"].exists()
    assert result["card_path"].exists()


def test_run_pipeline_with_progress_callback(tmp_path):
    events = []

    def callback(event):
        events.append(event)

    query = "test topic"
    run_pipeline(
        query=query,
        max_results=1,
        db_path=str(tmp_path / "loomset.db"),
        export_dir=str(tmp_path / "exports"),
        data_dir=str(tmp_path),
        labels=["relevant", "irrelevant"],
        callback=callback,
        seed_documents=[
            {
                "url": "https://example.com/test",
                "title": "Test",
                "text": "This is a test document about the test topic with enough content to pass quality filters.",
                "query": query,
            },
        ],
    )

    stages_seen = set(e["stage"] for e in events)
    assert "pipeline" in stages_seen
    assert "extraction" in stages_seen or "export" in stages_seen
