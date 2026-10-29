import tempfile
from pathlib import Path

import pandas as pd
import pytest

from loomset.cleaning.dedup import deduplicate_documents
from loomset.cleaning.quality_filter import quality_filter
from loomset.export.hf_export import assign_stratified_splits, create_passage_chunks, export_dataset
from loomset.labeling.ollama_manager import find_ollama_executable, is_ollama_running, resolve_best_model


def test_ollama_manager_executable_detection():
    # Detects the installed binary or gracefully returns None if absent
    exe = find_ollama_executable()
    assert exe is None or isinstance(exe, str)


def test_ollama_manager_running_check():
    # Returns boolean without throwing errors
    running = is_ollama_running()
    assert isinstance(running, bool)


def test_ollama_manager_resolve_best_model():
    # If no server running, returns empty string cleanly
    best = resolve_best_model()
    assert isinstance(best, str)


def test_near_duplicate_deduplication():
    doc1 = {
        "text": "Solar-punk urban planning focuses on renewable energy and community agriculture for green resilient cities.",
        "url": "https://example.com/doc1",
    }
    # 95% identical copy with minor footer noise
    doc2 = {
        "text": "Solar-punk urban planning focuses on renewable energy and community agriculture for green resilient cities. Copyright 2026 all rights reserved.",
        "url": "https://example.com/doc2",
    }
    doc3 = {
        "text": "Completely different article about baking artisan sourdough bread with whole wheat flour and yeast.",
        "url": "https://example.com/doc3",
    }

    results = deduplicate_documents([doc1, doc2, doc3], threshold=0.85)
    # doc2 should be recognized as a near-duplicate of doc1 and dropped
    assert len(results) == 2
    urls = [d["url"] for d in results]
    assert "https://example.com/doc1" in urls
    assert "https://example.com/doc3" in urls


def test_quality_filter_heuristics():
    # 1. High-quality natural text
    good_doc = {
        "text": (
            "Decentralized renewable microgrids provide cities with resilient power distribution during natural disasters. "
            "Urban planners incorporate solar rooftops, battery storage arrays, and local smart meters to ensure that "
            "neighborhoods can maintain emergency services without relying solely on regional fossil fuel grids."
        )
    }
    # 2. Low stopword ratio / spam keyword stuffing
    spam_doc = {
        "text": "solar urban city energy solar urban green solar power solar urban solar green solar urban solar solar city power"
    }
    # 3. Looping line repetition
    loop_doc = {
        "text": "\n".join(["Click here to subscribe now!"] * 10)
    }

    filtered = quality_filter([good_doc, spam_doc, loop_doc], min_text_length=50)
    assert len(filtered) == 1
    assert "Decentralized renewable" in filtered[0]["text"]
    assert filtered[0]["quality_score"] > 0.5


def test_ml_export_preserves_multiline_and_adds_splits():
    sample_records = [
        {
            "id": "doc-01",
            "url": "https://example.com/article1",
            "title": "Solar Energy Overview",
            "text": "# Solar Power\n\nSolar power is the conversion of energy from sunlight.\n\n- Photovoltaics\n- Solar thermal",
            "label": "clean_energy",
            "query": "solar energy",
        },
        {
            "id": "doc-02",
            "url": "https://example.com/article2",
            "title": "Wind Turbines",
            "text": "Wind power is the use of air flow through wind turbines.\n\nIt is an abundant renewable resource.",
            "label": "clean_energy",
            "query": "solar energy",
        },
        {
            "id": "doc-03",
            "url": "https://example.com/article3",
            "title": "Coal Mining",
            "text": "Coal mining is the process of extracting coal from the ground.\n\nIt produces carbon emissions.",
            "label": "fossil_fuels",
            "query": "solar energy",
        },
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        dataset_path, csv_path, parquet_path, card_path = export_dataset(sample_records, tmp_dir)

        # 1. Verify files exist
        assert dataset_path.exists()
        assert csv_path.exists()
        assert parquet_path.exists()
        assert card_path.exists()
        assert (Path(tmp_dir) / "dataset_chunks.csv").exists()

        # 2. Verify CSV preserves multiline markdown without flattening
        df = pd.read_csv(csv_path)
        assert len(df) == 3
        assert "\n" in df.loc[0, "text"]
        assert df.loc[0, "text"].startswith("# Solar Power")

        # 3. Verify ML schema columns
        required_cols = {"id", "text", "title", "label", "label_id", "confidence", "split", "word_count", "char_count", "token_estimate", "quality_score"}
        assert required_cols.issubset(set(df.columns))

        # 4. Verify categorical label IDs are integers
        assert pd.api.types.is_integer_dtype(df["label_id"])

        # 5. Verify stratified splits
        assert set(df["split"]).issubset({"train", "validation", "test"})


def test_passage_chunking():
    # Long text with > 500 words
    long_words = ["word"] * 600
    doc = {
        "id": "doc-long",
        "text": " ".join(long_words),
        "title": "Long Document",
        "label": "test",
        "label_id": 0,
        "split": "train",
    }
    chunks = create_passage_chunks([doc], chunk_words=300, overlap_words=30)
    assert len(chunks) >= 2
    assert chunks[0]["chunk_id"] == "doc-long_c0"
    assert chunks[1]["chunk_id"] == "doc-long_c1"
    assert chunks[0]["split"] == "train"
    assert chunks[1]["split"] == "train"

