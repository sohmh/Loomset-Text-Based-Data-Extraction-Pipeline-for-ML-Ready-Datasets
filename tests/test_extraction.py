from pathlib import Path

from loomset.extraction.trafilatura_extract import extract_text


def test_extract_text_extracts_main_content_from_fixture():
    html = Path("tests/fixtures/sample_article.html").read_text(encoding="utf-8")
    result = extract_text(html)
    assert result["text"] is not None
    assert "solar-punk" in result["text"].lower()
    assert result["lang"] in {"en", None}
