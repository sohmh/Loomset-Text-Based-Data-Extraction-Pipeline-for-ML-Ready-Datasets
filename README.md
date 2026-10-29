# LoomSet

LoomSet is a local, resumable pipeline for building text datasets on niche topics. It discovers real web pages, downloads and extracts their text, cleans and deduplicates records, assigns relevance labels, and exports the resulting text with source metadata. The local web interface streams progress from the same pipeline used by the CLI.

## What it does

- Searches across independent web search providers and uses Wikipedia article search as a full-text fallback. Provider failures are isolated so one unavailable backend does not stop discovery.
- Downloads discovered pages, with a Playwright Chromium fallback for pages that need JavaScript.
- Extracts and cleans text. Pages with no usable extracted text are excluded from the dataset.
- Labels each record `relevant` or `irrelevant` with Ollama when available, or with LoomSet's keyword fallback.
- Shows labeling progress and record previews in the web interface. The ledger includes clickable source URLs.
- Exports actual extracted text and provenance in JSON Lines, CSV, and Parquet formats.

Search coverage depends on external providers and the query. For focused topics, add specific seed URLs in the web interface when you already know useful authoritative sources. A seed URL is processed as a source page; it does not trigger a crawl of every link on that page.

## Requirements

- Python 3.11 or newer
- Internet access for discovery and page downloads
- Optional: [Ollama](https://ollama.com) for model-based labeling
- Optional: Playwright Chromium for JavaScript-heavy pages
- Optional: Label Studio to use the generated human-review batch

## Quick start — step by step

Follow these steps in order to clone, install, and verify the project.

### 1. Clone the repository

```bash
git clone <repo-url> LoomSet
cd LoomSet
```

### 2. Create and activate a virtual environment

**Windows PowerShell**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

> [!TIP]
> Any Python ≥ 3.11 works (including 3.12, 3.13, 3.14). Use whichever version you have installed — substitute `py -3.14` or `python3.12` as appropriate.

### 3. Install the package in editable mode

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

This installs all required dependencies (FastAPI, uvicorn, trafilatura, pandas, pyarrow, duckduckgo-search, etc.) and registers the `loomset` CLI command.

### 4. Run the test suite

```bash
pytest -q
```

All tests use local fixtures and run **offline** — no internet, Ollama server, or Playwright browser is needed. A passing run confirms the installation is correct.

### 5. Start the web interface

```bash
loomset serve --host 127.0.0.1 --port 8000
```

Or equivalently:

```bash
python -m uvicorn loomset.server:app --host 127.0.0.1 --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

> [!TIP]
> **Unified Local LLM**: LoomSet now includes an automated process supervisor. If [Ollama](https://ollama.com) is installed on your machine, LoomSet auto-starts the `ollama serve` background daemon automatically and auto-detects your best installed model—no need to manually start a separate terminal window! If Ollama is not installed, LoomSet runs its built-in semantic keyword scoring engine automatically.

### 6. Run a pipeline from the CLI (alternative to the web UI)

```bash
loomset run --query "solar-punk urban planning" --max-results 10
```

Pipeline state is stored in `data/loomset.db`; exports go to `data/exports/<query-slug>/`.

## Exported ML-grade records

LoomSet generates full-fidelity, training-ready datasets in RFC 4180 multiline CSV, JSON, and Apache Parquet formats:

- **Document-level dataset** (`dataset.csv`, `dataset.json`, `dataset.parquet`):
  Each record contains:
  - `id` (UUID), `text` (clean semantic Markdown), `title`
  - `label` (string) and categorical `label_id` (numeric integer)
  - `confidence` (float 0.0–1.0) and heuristic `quality_score` (0.0–1.0)
  - `split`: stratified 80% `train`, 10% `validation`, and 10% `test` partition
  - `word_count`, `char_count`, and `token_estimate`
  - Source provenance: `url`, `domain`, `language`, `fetched_at`, `label_source`, and `query`
- **Passage/Chunk-level dataset** (`dataset_chunks.csv`, `dataset_chunks.json`, `dataset_chunks.parquet`):
  Long documents are automatically broken into sliding-window passages (250–500 words with 10% overlap) formatted for standard Transformer context windows (BERT, RoBERTa, DeBERTa), RAG vector databases, and embedding fine-tuning.
- **Hugging Face Dataset Card** (`README.md`):
  Includes YAML frontmatter, label taxonomy (`label2id` / `id2label`), split distributions, token totals, and copy-paste Python code for `datasets.load_dataset` and `pandas`.

## Resuming and data

SQLite is the source of truth. LoomSet canonicalizes and deduplicates URLs, reuses existing document state, and avoids downloading completed URLs again. Search failures produce no results rather than fabricated placeholder URLs. The `seed_documents` argument in `run_pipeline` is a fixture hook for tests; it is not part of normal CLI or web discovery.

## Tests and architecture notes

Run the test suite with:

```bash
pytest -q
```

Tests use local fixtures and do not require live search or a running Ollama service by default. See [WORKING.md](WORKING.md) for the architecture and file-by-file guide.
