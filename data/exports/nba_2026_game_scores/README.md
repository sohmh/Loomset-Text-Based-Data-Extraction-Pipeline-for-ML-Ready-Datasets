---
annotations_creators:
- machine-generated
language_creators:
- found
language:
- en
license: cc-by-4.0
multilinguality:
- monolingual
size_categories:
- n<23
source_datasets:
- original
task_categories:
- text-classification
task_ids:
- multi-class-classification
---

# LoomSet Dataset: NBA 2026 Game Scores

This dataset was curated and structured with the **LoomSet ML Pipeline**. It is fully prepared for text classification, language modeling, RAG indexing, and fine-tuning.

## Dataset Summary

- **Total Documents**: 22
- **Total Passages (Chunks)**: 376
- **Estimated Total Tokens**: 147,973
- **Number of Classes**: 2
- **License**: CC-BY-4.0

## Splits Breakdown

| Split | Documents | Percentage |
|---|---|---|
| `test` | 2 | 9.1% |
| `train` | 17 | 77.3% |
| `validation` | 3 | 13.6% |

## Label Taxonomy (`label2id`)

| Label | Label ID | Documents |
|---|---|---|
| `irrelevant` | 0 | 15 |
| `relevant` | 1 | 7 |

## Data Fields

### Document-Level (`dataset.csv`, `dataset.json`, `dataset.parquet`)
- `id` (string): Unique document UUID.
- `text` (string): Cleaned semantic Markdown article content (RFC 4180 multiline quoted).
- `title` (string): Extracted page title.
- `label` (string): Assigned semantic category.
- `label_id` (integer): Categorical integer ID for PyTorch / Scikit-learn / Hugging Face.
- `confidence` (float): Model confidence score (0.0 to 1.0).
- `split` (string): Stratified partition (`train`, `validation`, `test`).
- `word_count` (integer): Word count.
- `char_count` (integer): Character count.
- `token_estimate` (integer): Estimated subword token count.
- `quality_score` (float): Heuristic text quality rating (0.0 to 1.0).
- `url` (string): Canonical source URL.
- `domain` (string): Origin domain.
- `language` (string): ISO language code.
- `fetched_at` (string): ISO 8601 ingestion timestamp.
- `label_source` (string): `auto` (LLM/semantic) or `human` (review).
- `query` (string): Topic search query.

### Passage-Level (`dataset_chunks.csv`, `dataset_chunks.json`, `dataset_chunks.parquet`)
- `chunk_id` (string): Passage identifier (`<doc_id>_c<idx>`).
- `doc_id` (string): Parent document UUID.
- `chunk_index` (integer): Position index in parent document.
- `text` (string): Passage text within standard Transformer token limits (250–500 words).
- `split` (string): Synchronized with parent document split (zero data leakage).

## Source Domains

- `en.wikipedia.org`
- `sportsbrackets.net`
- `www.landofbasketball.com`
- `www.nba.com`

## How to Load in Python

```python
from datasets import load_dataset
import pandas as pd

# 1. Hugging Face Datasets
dataset = load_dataset("parquet", data_files="data\exports\nba_2026_game_scores\dataset.parquet")
print(dataset)

# 2. Pandas (Full multiline markdown support)
df = pd.read_csv("data\exports\nba_2026_game_scores\dataset.csv")
print(df.groupby(['split', 'label']).size())
```
