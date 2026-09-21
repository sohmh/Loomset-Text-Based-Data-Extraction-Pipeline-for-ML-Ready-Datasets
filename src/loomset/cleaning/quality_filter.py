from __future__ import annotations

import re


def normalize_text(text: str) -> str:
    """Strip residual markdown/table noise and normalize whitespace."""
    lines = text.splitlines()
    clean = []
    for line in lines:
        s = line.strip()
        # Drop separator rows like |---|---|
        if re.match(r'^[|\s\-:]+$', s) and '|' in s:
            continue
        # Drop lines that are just pipe-delimited short values (table rows)
        if s.startswith('|') and s.endswith('|'):
            inner = s.strip('|')
            cells = [c.strip() for c in inner.split('|')]
            prose = ' '.join(c for c in cells if c)
            if len(prose) < 60:
                continue
        # Drop lines that have no letters at all (pure symbols/numbers)
        if s and not re.search(r'[A-Za-z]', s):
            continue
        clean.append(line)
    result = re.sub(r'\n{3,}', '\n\n', '\n'.join(clean))
    return result.strip()


def quality_filter(documents: list[dict], min_text_length: int = 200) -> list[dict]:
    kept = []
    for doc in documents:
        raw_text = doc.get("text") or ""
        # Normalize before quality checks
        text = normalize_text(raw_text)
        doc["text"] = text  # update in-place so cleaned text is stored
        if len(text) < min_text_length:
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        boilerplate_count = sum(1 for line in lines if any(token in line.lower() for token in ["home", "about", "contact", "menu", "login", "subscribe", "copyright"]))
        if len(lines) and boilerplate_count / len(lines) > 0.4:
            continue
        doc["quality_score"] = min(1.0, max(0.0, len(text) / (min_text_length * 2)))
        kept.append(doc)
    return kept
