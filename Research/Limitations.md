# Limitations

## Project: Text Based Data Extraction Pipeline for ML Ready Datasets

This document lists known limitations of the proposed open source pipeline, drawn both from constraints observed in the reviewed literature and from realistic constraints of an all free/opensource design.

---

### 1. Scraping Limitations
- **Legal & ethical boundaries:** As noted in the literature, scraping must respect a site's terms of service and `robots.txt`. Strict compliance means some data sources will simply be off limits, regardless of tooling  this is a hard ceiling on coverage, not just a technical one.
- **Structural fragility:** Websites frequently change their HTML structure. Even an adaptive scraper will periodically break on specific sites and require maintenance.
- **Access barriers:** CAPTCHAs, login walls, and IP based rate limiting/blocking cannot be reliably bypassed by free, ethical tooling. Paid services often work around these with rotating proxy pools an expense this project deliberately avoids, which caps what fraction of the web is reachable.
- **Completeness vs. speed trade-off:** As observed with BeautifulSoup based extraction, prioritizing speed can mean not all available data on a page is captured. Free/local extraction tools inherit some of this tradeoff, especially at scale.

### 2. Labelling Limitations
- **Lower accuracy than proprietary models:** Local opensource LLMs (via Ollama) and zero shot classifiers generally underperform large proprietary APIs on nuanced or highly domain specific labelling tasks, especially for niche topics with limited training signal.
- **Residual hallucination risk:** Even constrained to a fixed label set, local LLMs can still mislabel ambiguous or borderline text, an issue the literature flags for LLM based extraction/labelling generally.
- **Human review dependency:** For acceptable label quality on niche domains, a human in the loop step (Label Studio) is likely necessary, similar to the semi automated approach in prior work. This means the pipeline is not fully "hands-off" for every topic, only for cases where auto labelling confidence is high.
- **Domain generalization:** Auto labelling techniques such as distant-supervision NER (shown effective for a specific geological domain in the literature) may not generalize cleanly to arbitrary, user chosen topics without per topic tuning.

### 3. Scalability & Compute Limitations
- **Hardware constraints on "free" compute:** Running local LLMs for labelling still requires reasonable CPU/RAM, or a GPU for practical speed. Free tier options (e.g., Google Colab) come with session timeouts and usage caps, capping sustainable throughput.
- **No true zero marginal cost:** While no money is spent on APIs or subscriptions, local compute still consumes electricity and time; "free" refers to monetary cost, not to time or hardware requirements.
- **Throughput ceiling:** Without paid, horizontally scaled infrastructure, the pipeline is bound by whatever a single machine (or free-tier notebook) can process, limiting dataset size for very large scale use cases.

### 4. Data Quality Limitations
- **Web data noise:** Scraped text can include duplicated, low quality, or SEO spam content that automated cleaning may not fully filter out.
- **Coverage bias:** Because paid deep crawling services aren't used, the pipeline is more likely to miss "long tail" pages that are harder to discover organically, potentially skewing datasets toward more prominent/well indexed sources.

### 5. Privacy & Security Limitations
- **Unintentional PII capture:** Even scraping publicly available pages can incidentally capture personally identifiable information (names, emails, etc.). The pipeline does not currently guarantee automatic detection or redaction of such data.
- **No compliance guarantee:** Open source tooling does not, by itself, guarantee compliance with regulations such as GDPR or CCPA responsible use still depends on how the pipeline is configured and operated.

### 6. Scope Limitations
- **Text-only:** The current design and literature survey are scoped to text data; images, audio, and video extraction/labelling are out of scope for this prototype.
- **No direct benchmark yet:** A head to head quality/cost comparison against paid tools (FireCrawl, ScrapeGraphAI, LLM Scraper) has not been performed as part of this survey, since access to those tools at scale was itself cost-prohibitive the comparison remains a claim to be validated, not a demonstrated result.

### 7. Literature Access Limitations
- Some referenced papers had restricted full text access during the survey (e.g., the responsible-scraping paper), so certain claims in this project rely on abstracts or secondary summaries rather than complete papers, and should be revisited if full access becomes available.