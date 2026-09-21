from __future__ import annotations

import hashlib


def simple_hash(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def deduplicate_documents(documents: list[dict], threshold: float = 0.9) -> list[dict]:
    seen: dict[str, str] = {}
    kept: list[dict] = []
    for doc in documents:
        text = (doc.get("text") or "").strip()
        digest = simple_hash(text)
        if not text:
            continue
        if digest in seen:
            continue
        seen[digest] = text
        doc["dedup_hash"] = digest
        doc["quality_score"] = 1.0
        kept.append(doc)
    return kept
