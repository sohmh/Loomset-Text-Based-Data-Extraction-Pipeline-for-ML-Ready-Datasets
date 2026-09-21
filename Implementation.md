# LoomSet — MVP Implementation Plan

**Audience:** An autonomous coding agent (e.g. Claude Code) building this from scratch.
**Goal:** Ship a working, end-to-end version of the LoomSet pipeline — narrower in scope than the full research vision, but functionally complete: raw URLs in, a labeled, HuggingFace-ready dataset out. Every stage should run, even in a simplified form, so the system is demonstrable and extensible.

**Hard constraint: $0 monetary cost.** Every dependency must be free/open-source. Local compute and developer time are acceptable costs; paid APIs, paid proxies, and paid hosting are not.

---

## 1. What "MVP" means here

The full LoomSet architecture has 9 stages (URL Discovery → Static Scraping → Dynamic Scraping → Content Extraction → Storage → Cleaning → Auto-Labeling → Human Review → Export). The MVP implements **all nine stages**, but each stage is built at the simplest level that is still real (not mocked):

| Stage | Full vision | MVP scope |
|---|---|---|
| URL Discovery | Multi-source, deduped, query-expanded | Single query → DuckDuckGo search results, basic dedup |
| Static Scraping | Scrapy spiders, robots.txt-aware, retry/backoff | One Scrapy spider, robots.txt respected, simple retry |
| Dynamic Scraping | Full Playwright fallback for JS-heavy sites | Playwright fallback triggered only when static scrape yields near-empty content |
| Content Extraction | trafilatura + custom heuristics per domain | trafilatura only, default settings |
| Storage | SQLite + Parquet + DuckDB, versioned | SQLite as source of truth; Parquet export for the dataset table |
| Cleaning | Full dedup, language filtering, quality scoring, PII scrubbing | Near-duplicate detection (hash + simple similarity), language filter, boilerplate/length filters |
| Auto-Labeling | Ollama local LLM + Snorkel weak supervision ensemble | Ollama local LLM only, single labeling function, schema-constrained output |
| Human Review | Label Studio, full review workflows | Label Studio, single project template, accept/reject/edit only |
| Export | HuggingFace Datasets, versioned releases, dataset card | `datasets` library export to local disk + optional push to Hub, auto-generated dataset card |

**Definition of done for MVP:** running one command against a topic/query produces a HuggingFace `Dataset` object (and a Parquet file) with cleaned, labeled text records, having passed through every stage — with logs showing record counts surviving each stage.

---

## 2. Tech stack (confirmed, all free/OSS)

- **URL discovery:** `duckduckgo-search` (Python package); SearxNG as an optional self-hosted fallback (skip in MVP unless discovery yields too few results)
- **Static scraping:** `Scrapy`
- **Dynamic scraping:** `Playwright` (Python, headless Chromium)
- **Content extraction:** `trafilatura`
- **Storage:** `SQLite` (via `sqlite3`/`SQLAlchemy`) + `Parquet` (via `pandas`/`pyarrow`)
- **Auto-labeling:** `Ollama` (local LLM, e.g. `llama3.1:8b` or `qwen2.5:7b` — pick whatever the dev machine can run)
- **Human review:** `Label Studio` (local instance, `label-studio` pip package or Docker)
- **Export:** `datasets` (HuggingFace)
- **Language:** Python 3.11+
- **Config/orchestration:** plain Python + `pydantic` for config validation + `typer` or `click` for the CLI
- **Logging:** stdlib `logging`, structured (stage name, record counts, durations)

---

## 3. Repository structure

```
loomset/
├── pyproject.toml
├── README.md
├── config/
│   └── default.yaml
├── src/
│   └── loomset/
│       ├── __init__.py
│       ├── cli.py                  # entrypoint: `loomset run --query "..."`
│       ├── config.py                # pydantic config models + loader
│       ├── pipeline.py              # orchestrator: runs stages in sequence
│       ├── discovery/
│       │   ├── __init__.py
│       │   └── ddg_search.py
│       ├── scraping/
│       │   ├── __init__.py
│       │   ├── static_spider.py     # Scrapy spider
│       │   └── dynamic_fetch.py     # Playwright fallback
│       ├── extraction/
│       │   ├── __init__.py
│       │   └── trafilatura_extract.py
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── db.py                # SQLite schema + CRUD
│       │   └── models.py            # SQLAlchemy models
│       ├── cleaning/
│       │   ├── __init__.py
│       │   ├── dedup.py
│       │   ├── language_filter.py
│       │   └── quality_filter.py
│       ├── labeling/
│       │   ├── __init__.py
│       │   ├── ollama_client.py
│       │   └── label_schema.py
│       ├── review/
│       │   ├── __init__.py
│       │   └── label_studio_export.py   # push to LS, pull reviewed results back
│       └── export/
│           ├── __init__.py
│           └── hf_export.py
├── tests/
│   ├── test_discovery.py
│   ├── test_scraping.py
│   ├── test_extraction.py
│   ├── test_storage.py
│   ├── test_cleaning.py
│   ├── test_labeling.py
│   └── test_export.py
├── data/                             # gitignored — runtime artifacts
│   ├── raw/
│   ├── loomset.db
│   └── exports/
└── scripts/
    └── setup_ollama_model.sh
```

---

## 4. Environment setup

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install scrapy playwright trafilatura sqlalchemy pandas pyarrow duckduckgo-search ollama label-studio-sdk datasets pydantic typer huggingface-hub langdetect rapidfuzz`
3. `playwright install chromium`
4. Install Ollama separately (system package/binary — not pip) and pull a small local model: `ollama pull llama3.1:8b` (or a smaller model if the dev machine is constrained, e.g. `qwen2.5:3b`)
5. Label Studio: `pip install label-studio` and run `label-studio start` for local review, or leave dockerized as an alternative.

Pin versions in `pyproject.toml` once the agent has installed working versions; don't leave them unpinned.

---

## 5. Data schema (SQLite — source of truth)

```sql
CREATE TABLE documents (
    id            TEXT PRIMARY KEY,      -- uuid4
    url           TEXT NOT NULL,
    query         TEXT,                  -- discovery query that surfaced it
    domain        TEXT,
    fetch_method  TEXT,                  -- 'static' | 'dynamic'
    raw_html      TEXT,
    fetched_at    TIMESTAMP,
    status        TEXT DEFAULT 'fetched' -- fetched | extracted | cleaned | labeled | reviewed | exported | rejected
);

CREATE TABLE extracted_text (
    doc_id        TEXT PRIMARY KEY REFERENCES documents(id),
    title         TEXT,
    text          TEXT,
    lang          TEXT,
    extracted_at  TIMESTAMP
);

CREATE TABLE cleaned_text (
    doc_id        TEXT PRIMARY KEY REFERENCES documents(id),
    text          TEXT,
    dedup_hash    TEXT,
    quality_score REAL,
    cleaned_at    TIMESTAMP
);

CREATE TABLE labels (
    doc_id        TEXT PRIMARY KEY REFERENCES documents(id),
    label         TEXT,
    label_source  TEXT,      -- 'auto' | 'human'
    confidence    REAL,
    reviewed      BOOLEAN DEFAULT 0,
    labeled_at    TIMESTAMP
);
```

Every stage reads from one table/status and writes to the next — this makes the pipeline resumable and each stage independently testable/runnable on partial data.

---

## 6. Stage-by-stage build specs

### 6.1 URL Discovery (`discovery/ddg_search.py`)
- Input: a query string + target result count (config: `discovery.max_results`, default 50)
- Use `duckduckgo-search` to fetch result URLs for the query
- Dedup URLs (exact match), filter out obvious non-content domains (social media login pages, PDFs if out of scope for MVP — flag as config toggle)
- Output: list of `{url, query}` written into `documents` table with `status='discovered'`

### 6.2 Static Scraping (`scraping/static_spider.py`)
- A single generic Scrapy spider that takes a list of URLs (from `documents` where `status='discovered'`) and fetches raw HTML
- Respect `robots.txt` (Scrapy default), set a real User-Agent, basic retry (3 attempts, exponential backoff)
- On success: store `raw_html`, set `fetch_method='static'`, `status='fetched'`
- On failure or near-empty response (HTML body under a configurable char threshold, e.g. 500 chars): mark `status='needs_dynamic'` for stage 6.3

### 6.3 Dynamic Scraping (`scraping/dynamic_fetch.py`)
- For documents with `status='needs_dynamic'`: launch headless Playwright Chromium, navigate, wait for network idle (with timeout), grab rendered HTML
- Store `raw_html`, `fetch_method='dynamic'`, `status='fetched'`
- If it still fails: `status='failed'`, log and skip (don't crash the pipeline on one bad URL)

### 6.4 Content Extraction (`extraction/trafilatura_extract.py`)
- For all `status='fetched'` documents: run `trafilatura.extract()` on `raw_html`, get main text + title
- Detect language (`langdetect` or trafilatura's built-in) and store it
- Write to `extracted_text`, set `status='extracted'`
- If extraction returns empty/near-empty: `status='failed'`

### 6.5 Cleaning (`cleaning/`)
- **Dedup** (`dedup.py`): compute a content hash (e.g. SimHash or MinHash via `rapidfuzz`/simple shingling) per document; drop near-duplicates above a similarity threshold (config: `cleaning.dedup_threshold`, default 0.9)
- **Language filter** (`language_filter.py`): keep only documents in the target language(s) (config: `cleaning.languages`, default `["en"]`)
- **Quality filter** (`quality_filter.py`): drop documents below a minimum length (config default 200 chars) or with excessive boilerplate ratio (e.g. > 40% of lines look like nav/footer text — simple heuristics are fine for MVP, no ML model needed)
- Write to `cleaned_text`, set `status='cleaned'`

### 6.6 Auto-Labeling (`labeling/`)
- Define one labeling task/schema up front (config-driven — e.g. topic classification into a fixed label set, or a domain-relevance binary label). **The agent should pick one concrete, simple labeling task for the MVP demo** (e.g. binary "relevant to `<query>` domain: yes/no" or a small fixed topic taxonomy) rather than open-ended labeling.
- `label_schema.py`: a pydantic model constraining the LLM's output to the fixed label set (use Ollama's structured/JSON output mode if the chosen model supports it, else strict prompt + parse + validate + retry on parse failure)
- `ollama_client.py`: wraps calls to the local Ollama model, batches requests, handles timeouts/retries
- Write to `labels` with `label_source='auto'`, `status='labeled'`

### 6.7 Human Review (`review/label_studio_export.py`)
- Export `status='labeled'` documents + their auto-labels into a Label Studio project (via `label-studio-sdk`), using one simple template: show the cleaned text, show the predicted label, let the reviewer accept/reject/edit
- Pull-back function: after the user reviews in the Label Studio UI, fetch completed annotations via the SDK, update `labels` (`label_source='human'`, `reviewed=1`)
- This stage is semi-manual by design — the agent builds the push/pull integration; a human runs the actual review in the Label Studio UI

### 6.8 Export (`export/hf_export.py`)
- Pull all `status='reviewed'` (or `status='labeled'` if review was skipped) records with `cleaned_text` + `label`
- Build a `datasets.Dataset` (text, label, url, domain, label_source columns)
- Write Parquet to `data/exports/`
- Auto-generate a minimal dataset card (README.md with dataset description, source, size, label distribution, license — CC-BY or similar, license choice flagged for the user to confirm)
- Optional: push to HF Hub if a token is configured (must be opt-in, never automatic)

---

## 7. Orchestration & CLI

`pipeline.py` runs the stages in sequence, reading/writing the SQLite DB as the shared state, so any stage can also be re-run independently on partial data.

```
loomset run --query "solar-punk urban planning" --max-results 50 --labels relevant,irrelevant
loomset run-stage extract          # re-run just one stage on existing DB
loomset status                     # print record counts per status
loomset export --push-to-hub false
```

Use `typer` for the CLI. Every stage function should be callable both from the CLI and directly as a Python function (for tests and notebooks).

---

## 8. Testing

- Unit tests per module with small fixtures (a handful of sample HTML pages checked into `tests/fixtures/`, not live network calls)
- One integration test that runs the full pipeline against 3–5 fixed, checked-in HTML fixtures (no live scraping) and asserts a non-empty exported dataset at the end
- Mark real-network tests (`discovery`, live `scraping`) as `@pytest.mark.integration`, skipped by default in CI

---

## 9. Build order (suggested milestones for the agent)

1. **Scaffold** repo structure, `pyproject.toml`, config loader, SQLite schema/models
2. **Stage 1–2**: discovery + static scraping, verify raw HTML lands in the DB for a real query
3. **Stage 3–4**: dynamic fallback + extraction, verify clean text lands in `extracted_text`
4. **Stage 5**: cleaning filters, verify record counts drop sensibly (log before/after per filter)
5. **Stage 6**: auto-labeling against a single fixed schema, verify labels parse and validate
6. **Stage 7**: Label Studio push/pull integration (can be stubbed/tested against a local LS instance)
7. **Stage 8**: HF export, verify a loadable `Dataset` and dataset card are produced
8. **CLI wiring + `loomset run` end-to-end smoke test** on one real query
9. **Tests** (fixtures + integration test) added alongside each stage, not bolted on at the end

---

## 10. Explicitly out of scope for MVP (future work)

- SearxNG multi-source discovery
- Snorkel weak-supervision ensembling (multiple labeling functions)
- DuckDB analytical layer
- Per-domain extraction heuristics beyond trafilatura defaults
- PII scrubbing
- Multi-language support beyond one target language
- Versioned dataset releases / full HF Hub release workflow
- Any paid API or proxy service

---

## 11. Notes for the agent

- Every stage must be **resumable**: never assume a clean-slate run; always filter by `status` before processing.
- **Fail soft per-document, fail loud per-stage**: one bad URL shouldn't crash the pipeline, but a stage that processes zero records should log a clear warning.
- Log record counts entering/leaving every stage — this is the primary way the user will sanity-check the pipeline without reading code.
- Keep config in `config/default.yaml`, loaded via `pydantic`, no hardcoded queries/paths/thresholds in code.
- Favor the simplest correct implementation over a general one — this is scoped as an MVP that will be iterated on, not a final architecture.