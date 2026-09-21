# LoomSet

LoomSet is a local, resumable dataset-generation pipeline. It discovers URLs, downloads static pages with a dynamic fallback, extracts and cleans text, labels records with Ollama, prepares human review, and exports Hugging Face, JSON, CSV, and Parquet artifacts.

## Requirements

- Python 3.11 or newer
- Internet access for discovery and downloading
- Optional: Ollama for automatic labeling
- Optional: Chromium installed through Playwright for JavaScript-heavy pages
- Optional: Label Studio for human review

## Setup

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m playwright install chromium
```

### Linux or macOS

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m playwright install chromium
```

## Connect Ollama for labeling

Install Ollama from [ollama.com](https://ollama.com). Then use a second PowerShell terminal for Ollama:

```powershell
ollama serve
ollama pull qwen3:8b
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

Keep that terminal running. In another terminal, start LoomSet:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn loomset.server:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000`, enter a query, and run the pipeline. During the labeling stage LoomSet sends each cleaned text to Ollama at `http://localhost:11434/api/generate` using the `qwen3:8b` model and expects JSON containing `label` and `confidence`.

You can verify the LoomSet-side connection at `http://localhost:8000/api/ollama/status`. To use another installed model, update `labeling.ollama_model` and `labeling.ollama_url` in `config/default.yaml`, for example:

```yaml
labeling:
	ollama_model: "llama3.2:3b"
	ollama_url: "http://localhost:11434"
```

If Ollama is unavailable or the selected model is missing, LoomSet uses its built-in keyword fallback for labeling rather than stopping the pipeline.

## Run

From the repository root, with the virtual environment active:

```bash
loomset run --query "solar-punk urban planning" --max-results 10
```

The command writes SQLite state to `data/loomset.db` and query-specific exports to `data/exports/<query-slug>/`. It also refreshes the root `data/exports` files with the latest seam for compatibility with the web UI.

Useful commands:

```bash
loomset status
loomset run-stage discovery --query "solar-punk urban planning" --max-results 10
loomset run-stage scraping
loomset run-stage extraction
loomset run-stage cleaning
loomset run-stage labeling --labels relevant,irrelevant
loomset run-stage review
loomset run-stage export
python -m uvicorn loomset.server:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000` after starting the server to use the local interface. The equivalent installed CLI command is `loomset serve --host 127.0.0.1 --port 8000`.

## Incremental downloads

SQLite is the source of truth. URLs are canonicalized and unique, so rediscovering an existing URL reuses its document and preserves its progress. Only URLs newly inserted with `status='discovered'` are downloaded. A later run therefore adds only newly discovered pages and does not refetch completed seams. Search failures return an empty discovery result; LoomSet never turns a fabricated placeholder URL into downloaded dataset content.

The `seed_documents` argument in `run_pipeline` is a fixture/testing hook that creates in-memory HTML records. It is not used by the CLI or production discovery path.

## Tests

```bash
pytest -q
```

Tests use checked-in fixtures and do not require live search or a running Ollama service by default. See [WORKING.md](WORKING.md) for the full architecture and file-by-file guide.
