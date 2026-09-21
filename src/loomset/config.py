from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    name: str = "loomset"
    data_dir: str = "data"
    db_path: str = "data/loomset.db"
    export_dir: str = "data/exports"


class LoggingConfig(BaseModel):
    level: str = "INFO"


class QueryConfig(BaseModel):
    max_results: int = 10


class ScrapingConfig(BaseModel):
    min_html_chars: int = 500
    dynamic_fallback: bool = True


class SearchConfig(BaseModel):
    max_results: int = 10


class CleaningConfig(BaseModel):
    dedup_threshold: float = 0.9
    min_text_length: int = 100
    languages: list[str] = Field(default_factory=lambda: ["en"])


class LabelingConfig(BaseModel):
    default_label: str = "relevant"
    allowed_labels: list[str] = Field(default_factory=lambda: ["relevant", "irrelevant"])
    ollama_model: str = ""
    ollama_url: str = "http://localhost:11434"


class ExportConfig(BaseModel):
    push_to_hub: bool = False


class AppConfig(BaseModel):
    project: ProjectConfig = ProjectConfig()
    logging: LoggingConfig = LoggingConfig()
    query: QueryConfig = QueryConfig()
    search: SearchConfig = SearchConfig()
    scraping: ScrapingConfig = ScrapingConfig()
    cleaning: CleaningConfig = CleaningConfig()
    labeling: LabelingConfig = LabelingConfig()
    export: ExportConfig = ExportConfig()


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path) if path else Path(__file__).resolve().parents[2] / "config" / "default.yaml"
    with open(config_path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return AppConfig(**raw)


def get_default_config() -> AppConfig:
    return load_config()
