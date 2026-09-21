# How LoomSet Works

This document is the implementation guide for the repository. LoomSet is a local, resumable pipeline whose source of truth is SQLite. A run moves each document through discovery, scraping, extraction, cleaning, labeling, review, and export. Every stage is also exposed as a Python function and most stages are available through `loomset run-stage`.

## End-to-end flow

1. A query is sent to DuckDuckGo and, when available, Wikipedia OpenSearch supplies additional results.
2. URLs are filtered and canonicalized. SQLite stores one document per canonical URL.
3. Static HTTP fetching downloads newly discovered pages. Pages that fail or are too short are sent to the dynamic fetcher.
4. Playwright renders JavaScript-heavy pages when installed. A failed page is marked `failed` and does not stop the run.
5. Trafilatura extracts the article title and main text. Empty extraction is persisted as `failed`.
6. Cleaning removes exact duplicate text, filters languages, and applies minimum-quality/length rules.
7. Ollama assigns one of the configured labels, normally `relevant` or `irrelevant`.
8. A Label Studio-compatible JSON batch is written and labeled records are marked ready for review. Human import/export helpers update labels when review results are supplied.
9. Reviewed or labeled records are exported as Hugging Face Dataset JSON, CSV, Parquet, and a dataset card.

The normal status progression is `discovered -> fetched -> extracted -> cleaned -> labeled -> reviewed`. A failed scrape or extraction is terminal for that document until an operator changes or retries it deliberately.

## Incremental behavior and identity

`src/loomset/discovery/ddg_search.py` and `src/loomset/storage/db.py` use the same URL identity rules: lowercase scheme and hostname, remove default ports, remove fragments, and remove a trailing path slash. `documents.url` is unique and `upsert_document` returns `True` only for a newly inserted URL.

`stage_discovery` returns only newly inserted records. Rediscovery does not replace an existing raw page, status, labels, or cleaned text. `stage_scraping` reads only `status='discovered'`, so a completed document cannot be downloaded again during a later seam. `export_dataset` applies the same canonical identity as a final defense against duplicate exported URLs.

The old synthetic discovery fallback has been removed. If search and Wikipedia return no usable results, discovery returns an empty list. The CLI never downloads fabricated `example.com` pages. `run_pipeline(seed_documents=...)` remains only as a fixture hook for deterministic tests; it deliberately bypasses network discovery and should not be used for production data.

## Storage tables

- `documents`: URL identity, query, domain, raw HTML, fetch method, timestamp, and current status.
- `extracted_text`: title, extracted text, detected language, and extraction timestamp.
- `cleaned_text`: filtered text, content hash, quality score, and cleaning timestamp.
- `labels`: label, source (`auto` or `human`), confidence, review flag, and timestamp.

The database is created automatically at the configured path. The application uses standard-library `sqlite3`; SQLAlchemy is retained as an available project dependency for future model work.

## Configuration

`config/default.yaml` contains project paths, logging, result limits, scraping thresholds, cleaning rules, allowed languages, Ollama connection settings, and export options. `src/loomset/config.py` loads that YAML into Pydantic models. Paths are relative to the working directory when supplied in the configuration.

## File-by-file reference

### Root files

- `Implementation.md`: original MVP requirements, stage contracts, schema, build order, and scope boundaries.
- `README.md`: setup, commands, runtime prerequisites, incremental semantics, and test instructions.
- `WORKING.md`: this detailed architecture and operational reference.
- `index.html`: the local browser dashboard served by FastAPI.
- `pyproject.toml`: package metadata, Python requirement, dependencies, setuptools configuration, and the `loomset` console entry point.
- `config/default.yaml`: default runtime configuration.

### Package entry points and orchestration

- `src/loomset/__init__.py`: package marker and public package metadata.
- `src/loomset/cli.py`: Typer commands for running the full pipeline, running stages, printing status, and starting the server.
- `src/loomset/config.py`: Pydantic configuration models and YAML loader.
- `src/loomset/pipeline.py`: stage orchestration, progress events, fixture seeding, status summaries, query-slug export paths, and the full `run_pipeline` entry point.
- `src/loomset/server.py`: FastAPI application, dashboard/static-file serving, health/status APIs, dataset APIs, downloads, and synchronous or streamed pipeline execution.

### Discovery

- `src/loomset/discovery/__init__.py`: discovery package marker.
- `src/loomset/discovery/ddg_search.py`: DuckDuckGo and Wikipedia lookup, content-domain filtering, URL normalization, URL deduplication, and conversion of URLs into document records. It intentionally has no fabricated fallback URLs.

### Scraping

- `src/loomset/scraping/__init__.py`: scraping package marker.
- `src/loomset/scraping/static_spider.py`: static HTTP fetch helper, user-agent, short-response handling, text hashing, and the generic static batch helper used by the pipeline.
- `src/loomset/scraping/dynamic_fetch.py`: Playwright Chromium renderer with a requests fallback when Playwright is unavailable, plus document status updates for success/failure.

### Extraction

- `src/loomset/extraction/__init__.py`: extraction package marker.
- `src/loomset/extraction/trafilatura_extract.py`: metadata/title extraction, main-text extraction, table-artifact cleanup, language detection, and per-document extraction status.

### Storage

- `src/loomset/storage/__init__.py`: storage package marker.
- `src/loomset/storage/db.py`: SQLite schema creation, connections, document queries, URL-canonicalizing upsert, status updates, and CRUD helpers for extracted text, cleaned text, and labels.

### Cleaning

- `src/loomset/cleaning/__init__.py`: cleaning package marker.
- `src/loomset/cleaning/dedup.py`: normalized content hashing and exact duplicate removal.
- `src/loomset/cleaning/language_filter.py`: allowed-language filtering.
- `src/loomset/cleaning/quality_filter.py`: minimum-length and quality filtering.

### Labeling

- `src/loomset/labeling/__init__.py`: labeling package marker.
- `src/loomset/labeling/label_schema.py`: Pydantic validation for the fixed label result shape and allowed labels.
- `src/loomset/labeling/ollama_client.py`: Ollama availability checks, client creation, prompt construction, response parsing, retries, and local-model labeling.

### Review and export

- `src/loomset/review/__init__.py`: review package marker.
- `src/loomset/review/label_studio_export.py`: conversion of labeled records into Label Studio task JSON.
- `src/loomset/export/__init__.py`: export package marker.
- `src/loomset/export/hf_export.py`: canonical URL deduplication, Hugging Face Dataset construction, JSON/CSV/Parquet writing, and dataset-card generation.

### Runtime data

- `data/exports/`: default runtime export location. Query-specific runs are stored in subdirectories and the root files are synchronized for the dashboard.
- `data/exports/dataset.csv`, `dataset.json`, and `README.md`: root export views and generated dataset card.
- `data/exports/nascar/`: a query-specific checked-in export containing CSV, JSON, and dataset-card files for the NASCAR seam.
- `data/review/label_studio_batch.json`: default review batch location.
- `src/data/exports/dataset.csv`, `dataset.json`, and `README.md`: checked-in reference export for the harness-engineering seam.
- `src/data/exports/harness_engineering/`: query-specific copy of that reference export, with CSV, JSON, and dataset-card files.
- `src/loomset.egg-info/dependency_links.txt`, `entry_points.txt`, `PKG-INFO`, `requires.txt`, `SOURCES.txt`, and `top_level.txt`: setuptools-generated installation metadata; they are not pipeline logic.

### Tests

- `tests/test_cli.py`: command-line behavior.
- `tests/test_discovery.py`: URL filtering, duplicate removal, and search-result handling.
- `tests/test_dynamic_scraping.py`: dynamic fetch behavior.
- `tests/test_extraction.py`: extraction against the checked-in HTML fixture.
- `tests/test_pipeline.py`: fixture-backed end-to-end pipeline and progress events.
- `tests/test_review.py`: review-batch serialization.
- `tests/test_server.py`: FastAPI endpoint behavior.
- `tests/test_storage.py`: URL identity, one-row rediscovery, and progress preservation.
- `tests/test_export.py`: canonical export deduplication and empty-export artifacts.
- `tests/fixtures/sample_article.html`: deterministic article HTML used without live network access.

## Operating the project

Install the package with the setup commands in `README.md`, then run `loomset run --query "your topic"`. Use `loomset status` to inspect the SQLite state. If a stage needs to be rerun, use `loomset run-stage <stage>`; completed documents are not re-downloaded because scraping consumes only newly discovered rows.

For local browser use, run `loomset serve --port 8000` and open `http://localhost:8000`. The API exposes health, Ollama status, pipeline execution, status summaries, dataset previews, and safe download endpoints.

Run the test suite with `pytest -q`. The tests are designed to work offline except for tests explicitly marked as integration in future extensions. Ollama and Chromium are runtime integrations, not requirements for the fixture-backed extraction and pipeline tests.

## Known operational boundaries

- Discovery depends on external search services and may legitimately produce zero URLs.
- Ollama labeling requires a running local Ollama server and a pulled model; labeling can be run independently after cleaning.
- Playwright requires its browser binary for true JavaScript rendering. The fallback request is useful for environments where browser installation is unavailable, but it cannot execute page JavaScript.
- License and source rights remain the operator's responsibility. The generated card currently marks the dataset as CC-BY with a confirmation reminder.
