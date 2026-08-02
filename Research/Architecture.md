# Architecture

## Project: Text Based Data Extraction Pipeline for ML Ready Datasets

**Constraint:** Every component below is open-source or free tier, so the prototype can be built and run at zero monetary cost. Where a paid tool from the literature survey (FireCrawl, ScrapeGraphAI, LLM Scraper) had a free/open-source functional equivalent, that equivalent was chosen instead.

---

## 1. Pipeline Overview

![Pipeline](https://github.com/sohmh/Loomset-Text-Based-Data-Extraction-Pipeline-for-ML-Ready-Datasets/blob/main/Diagrams/Workflow.png)

The pipeline is organized as seven stages. Each stage is a swappable, independent module so components can be upgraded later without redesigning the whole system.

---

## 2. Stage by Stage Design

### Stage 1 : Topic Input & URL Discovery
- **Tool:** `duckduckgo-search` (Python package, free, no API key) or a self-hosted **SearxNG** instance (open-source metasearch engine).
- **Why:** Avoids paid search APIs (Google Custom Search, Bing Search API) while still providing automated URL discovery for a given topic, directly addressing the "URL discovery constraints" limitation noted for FireCrawl.
- **Output:** A candidate list of URLs per topic/query.

### Stage 2 : Scraping Layer
- **Tools:**
  - **Scrapy** : for static/simple HTML pages, respects `robots.txt` by default, handles concurrency and retries.
  - **Playwright** (open-source headless browser) : for JavaScript-rendered/dynamic pages, functioning as a free substitute for the "headless surfing" capability described in the adaptive scraping framework literature.
- **Why:** Combining a lightweight crawler with a headless browser covers both static and dynamic sites without per-page credit costs.

### Stage 3 : Content Extraction & Cleaning
- **Tools:**
  - **trafilatura** (open-source) : purpose built for extracting main article/body text and stripping boilerplate (nav bars, ads, footers). This directly addresses the completeness vs speed limitation noted in the BeautifulSoup based paper.
  - **BeautifulSoup4 / lxml** : fallback parser for structured/simple pages.
  - **langdetect** or **fastText language-ID model** : filters out non target language content.
  - **datasketch (MinHash)** : near duplicate detection to remove redundant scraped content.
  - **regex / NLTK / spaCy** : normalization, sentence segmentation, tokenization.
- **Output:** Clean, deduplicated plain text records with metadata (source URL, timestamp, language).

### Stage 4 : Storage Layer
- **Tools:** **SQLite** (embedded, zero config, free) for metadata/indexing, plus flat files (**Parquet** via `pyarrow`, or JSONL) for the actual text records.
- **Why:** No database server, no hosting cost, fully portable, works identically on a laptop or a free tier cloud notebook.

### Stage 5 : Auto-Labelling Layer
- **Tools:**
  - **Ollama** running a local open-source LLM (e.g., Llama 3.1 8B, Mistral 7B, Qwen2.5) for topic/category labelling and zero-shot classification, a free, local substitute for the "LLM Scraper" approach, avoiding both its API cost and part of its hallucination risk since output can be constrained to a fixed label set.
  - **HuggingFace `transformers`** open models (e.g., `facebook/bart large mnli` for zero shot classification, open NER models) as a lighter weight alternative when a full LLM isn't necessary.
- **Why:** Directly fills the gap identified in the survey : "no tools right now can also label the extracted data" ; using only free, locally run models.

### Stage 6 : Human in the Loop QA (optional, semi automated mode)
- **Tool:** **Label Studio** (opensource, self hosted).
- **Why:** Mirrors the semi automated labelling approach from the literature (predictive model assists a human labeler), used selectively for records where the auto labeller has low confidence.

### Stage 7 : Dataset Export
- **Tool:** HuggingFace **`datasets`** library.
- **Why:** Packages the final cleaned, labelled records into a standard ML ready format (JSONL / Arrow / CSV) that plugs directly into common training pipelines.

---

## 3. Orchestration & Compute
- **Orchestration:** Plain Python scripts driven by a YAML/JSON config for the prototype; **Prefect Core** (opensource) if scheduling/retries across stages are needed later.
- **Compute:** Local CPU, or free-tier GPU via Google Colab for LLM based labelling : no paid cloud credits required at any stage.
- **Version tracking (optional):** **DVC** (Data Version Control, opensource) to track dataset versions as the pipeline is re-run.

---

## 4. Technology Summary Table

| Stage | Tool(s) | License / Cost |
|---|---|---|
| URL Discovery | duckduckgo-search / SearxNG | Free / Open-source |
| Static Scraping | Scrapy | Open-source (BSD) |
| Dynamic Scraping | Playwright | Open-source (Apache 2.0) |
| Content Extraction | trafilatura, BeautifulSoup4 | Open-source |
| Dedup / Lang ID | datasketch, langdetect | Open-source |
| Storage | SQLite, Parquet (pyarrow) | Open-source / built into Python |
| Auto-Labelling | Ollama + local LLM, HF transformers | Open-source (model-dependent license) |
| Human Review | Label Studio | Open-source |
| Dataset Export | HuggingFace `datasets` | Open-source |
| Orchestration | Python / Prefect Core | Open-source |
| Compute | Local CPU / Colab free tier | Free |

---

## 5. Design Principles Followed
1. **No paid APIs or per-credit services anywhere in the pipeline**, directly answering the cost limitations noted for FireCrawl, ScrapeGraphAI, and LLM Scraper.
2. **Modularity** : each stage can be swapped (e.g., a different local LLM, a different scraper) without touching the rest of the pipeline.
3. **Ethical by default scraping** : `robots.txt` compliance and rate limiting are built into the scraping layer rather than left as an afterthought.
4. **Labelling as a first-class stage**, not an external step : the identified gap in existing tools.
