import json

from loomset.export.hf_export import export_dataset


def test_export_deduplicates_canonical_urls_and_supports_empty_dataset(tmp_path):
    paths = export_dataset(
        [
            {"text": "one", "url": "https://Example.com/article/", "label": "relevant"},
            {"text": "duplicate", "url": "https://example.com/article", "label": "irrelevant"},
        ],
        tmp_path / "export",
    )
    assert all(path.exists() for path in paths)
    exported_rows = [json.loads(line) for line in paths[0].read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(exported_rows) == 1
    assert exported_rows[0]["url"] == "https://example.com/article"

    empty_paths = export_dataset([], tmp_path / "empty")
    assert all(path.exists() for path in empty_paths)