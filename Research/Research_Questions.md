# Research Questions

## Project: Text Based Data Extraction Pipeline for ML Ready Datasets

These questions were derived from the gaps identified in the literature survey: existing tools (FireCrawl, ScrapeGraphAI, LLM Scraper) are costly at scale, none offer built-in labelling, and no single open-source pipeline currently unifies scraping, cleaning, and labelling for niche-topic ML datasets.

---

### Primary Research Question

**RQ0:** Can a fully open source, zero cost pipeline be designed that scrapes, cleans, and labels topic specific text data at a quality sufficient for training machine learning models without relying on paid APIs or per-credit scraping services?

---

### Web Scraping & Data Collection

**RQ1:** How can an open-source scraping layer (e.g., Scrapy, Playwright) be designed to adapt to the structural diversity of websites, matching the flexibility claimed by paid tools like FireCrawl, without their credit based cost model?

**RQ2:** What is the practical tradeoff between extraction completeness and scraping speed when using free/open source libraries (e.g BeautifulSoup, trafilatura), and how can this tradeoff be tuned per use case rather than fixed, as noted as a limitation in existing BeautifulSoup based approaches?

**RQ3:** How should a pipeline discover relevant URLs for a niche topic without relying on paid search APIs (e.g., using open-source/free alternatives such as DuckDuckGo search or self hosted metasearch engines)?

### Data Cleaning, Storage & Structuring

**RQ4:** What preprocessing steps (deduplication, boilerplate removal, language filtering, normalization) are necessary to convert raw scraped HTML into clean, ML ready text, and which open source libraries can perform these reliably at low compute cost?

**RQ5:** What lightweight, free storage format (e.g., SQLite, Parquet, flat JSONL) best balances queryability and portability for a dataset generation pipeline meant to scale from prototype to moderate size?

### Automated / Semi-Automated Labelling

**RQ6:** Can open-source, locally run LLMs (e.g., via Ollama) or zero shot classification models perform text labelling at an accuracy usable for ML training, addressing the gap that "no tools right now can also label the extracted data"?

**RQ7:** Following the semi automated labelling approach in prior work (Desmond et al., 2021), how effective is a human-in-the-loop review step (e.g., via an open-source tool like Label Studio) at correcting auto generated labels while keeping overall labelling cost at zero?

**RQ8:** How well do distant supervision or iterative NER style auto labelling techniques (as applied to low resource/domain specific text) generalize to arbitrary niche topics chosen by a user, rather than a single fixed domain?

### Scalability & Compute Efficiency

**RQ9:** What scraping and labelling throughput is achievable using only free tier compute (local CPU, free-tier cloud notebooks) and how does this constrain the maximum practical dataset size for the pipeline?

### Ethics, Privacy & Legal Compliance

**RQ10:** How can the pipeline enforce responsible scraping practices (robots.txt compliance, rate limiting, avoiding personally identifiable information) automatically, rather than leaving this to the end user?

### Evaluation

**RQ11:** How does the quality (label accuracy, data completeness, noise level) of datasets produced by this open-source pipeline compare to datasets produced manually or via existing paid tools?