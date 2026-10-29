from __future__ import annotations

import hashlib
import re
from typing import Any

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None


def simple_hash(text: str) -> str:
    """Return a normalized SHA-256 hash of the text content."""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _get_shingle_set(text: str, n: int = 3) -> set[str]:
    words = re.findall(r"\w+", text.lower())
    if len(words) < n:
        return set(words)
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def _jaccard_similarity(s1: set[str], s2: set[str]) -> float:
    if not s1 or not s2:
        return 0.0
    intersection = len(s1 & s2)
    union = len(s1 | s2)
    return intersection / union if union > 0 else 0.0


def deduplicate_documents(documents: list[dict[str, Any]], threshold: float = 0.88) -> list[dict[str, Any]]:
    """Deduplicate documents using both exact hashing and near-duplicate fuzzy matching.

    Parameters:
        documents: List of document dicts with a 'text' field.
        threshold: Jaccard / Fuzzy similarity threshold (0.0 to 1.0) above which
                   a document is considered a near-duplicate of an already-seen document.
    """
    seen_hashes: set[str] = set()
    kept_shingles: list[tuple[set[str], str]] = []  # (shingles, sample_snippet)
    kept: list[dict[str, Any]] = []

    for doc in documents:
        text = (doc.get("text") or "").strip()
        if not text:
            continue

        digest = simple_hash(text)
        if digest in seen_hashes:
            continue

        # Near-duplicate check against already accepted documents
        doc_shingles = _get_shingle_set(text)
        is_near_dup = False

        # Fast 3-gram Jaccard filter
        for existing_shingles, existing_sample in kept_shingles:
            jaccard = _jaccard_similarity(doc_shingles, existing_shingles)
            if jaccard >= threshold:
                is_near_dup = True
                break
            # If shingle overlap is high, double-check with RapidFuzz token_set_ratio
            if jaccard >= (threshold * 0.75) and fuzz is not None:
                ratio = fuzz.token_set_ratio(text[:1500], existing_sample[:1500]) / 100.0
                if ratio >= threshold:
                    is_near_dup = True
                    break

        if is_near_dup:
            continue

        seen_hashes.add(digest)
        kept_shingles.append((doc_shingles, text[:1500]))
        doc["dedup_hash"] = digest
        doc["quality_score"] = doc.get("quality_score", 1.0)
        kept.append(doc)

    return kept
