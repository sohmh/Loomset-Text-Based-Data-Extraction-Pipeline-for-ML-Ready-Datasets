from __future__ import annotations


def filter_language(documents: list[dict], languages: list[str] | None = None) -> list[dict]:
    allowed = set((languages or ["en"]))
    filtered = []
    for doc in documents:
        lang = doc.get("lang")
        if lang is None:
            if "en" in allowed:
                filtered.append(doc)
            continue
        if lang in allowed:
            filtered.append(doc)
    return filtered
