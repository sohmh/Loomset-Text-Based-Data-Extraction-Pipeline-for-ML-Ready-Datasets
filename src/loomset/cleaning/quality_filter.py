from __future__ import annotations

import re
import unicodedata
from typing import Any

# Standard English functional stopwords for text quality validation
_COMMON_STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "can", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "he", "her", "here", "him", "his", "how", "i", "if", "in",
    "into", "is", "it", "its", "just", "me", "more", "most", "my", "no", "nor", "not", "now",
    "of", "off", "on", "once", "only", "or", "other", "our", "out", "over", "own", "same", "she",
    "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "then",
    "there", "these", "they", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom", "why",
    "with", "would", "you", "your"
}

_BOILERPLATE_TOKENS = {
    "cookie", "privacy policy", "terms of use", "terms of service", "all rights reserved",
    "sign in", "log in", "subscribe", "newsletter", "copyright", "accept all", "manage cookies",
    "skip to content", "read more", "share on facebook", "share on twitter", "back to top"
}


def normalize_text(text: str) -> str:
    """Normalize text encoding, strip unprintable chars and residual table noise."""
    if not text:
        return ""

    # 1. Unicode NFKC normalization
    text = unicodedata.normalize("NFKC", text)

    # 2. Strip unprintable control chars and zero-width spaces (keep \n, \t, \r)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b\u200c\u200d\ufeff\ufffd]", "", text)

    lines = text.splitlines()
    clean: list[str] = []
    for line in lines:
        s = line.strip()
        if not s:
            clean.append("")
            continue

        # Drop markdown table separator rows like |---|---|
        if re.match(r"^[|\s\-:]+$", s) and "|" in s:
            continue

        # Drop lines that are pure pipe table cells with under 40 characters
        if s.startswith("|") and s.endswith("|"):
            inner = s.strip("|")
            cells = [c.strip() for c in inner.split("|")]
            prose = " ".join(c for c in cells if c)
            if len(prose) < 40:
                continue

        # Drop lines that have no letters at all (e.g. pure punctuation or digits)
        if s and not re.search(r"[A-Za-z\u00C0-\u024F\u0400-\u04FF]", s):
            continue

        clean.append(line)

    result = re.sub(r"\n{3,}", "\n\n", "\n".join(clean))
    return result.strip()


def calculate_quality_score(text: str, words: list[str], lines: list[str]) -> tuple[float, bool]:
    """Evaluate text quality using FineWeb/Dolma heuristic signals.

    Returns:
        (quality_score, is_acceptable)
    """
    if not words or not lines:
        return 0.0, False

    total_words = len(words)
    total_chars = sum(len(w) for w in words)
    mean_word_length = total_chars / total_words

    # Rule 1: Mean word length should be between 3.0 and 11.0 characters
    if mean_word_length < 2.5 or mean_word_length > 12.0:
        return 0.1, False

    # Rule 2: Stopword ratio check (Natural English typically has 25% - 70% stopwords)
    stopword_count = sum(1 for w in words if w.lower() in _COMMON_STOPWORDS)
    stopword_ratio = stopword_count / total_words
    if stopword_ratio < 0.10 and total_words >= 15:
        # Likely keyword spam, OCR dump, or raw table data
        return 0.2, False

    # Rule 3: Symbol-to-word ratio (Should not be an ASCII art or symbol flood)
    raw_symbols = len(re.findall(r"[#$%&*+<=>@\\^`|~]", text))
    symbol_ratio = raw_symbols / total_words
    if symbol_ratio > 0.20:
        return 0.2, False

    # Rule 4: Repetitive text filtering (Detect scrape looping)
    non_empty_lines = [l.strip().lower() for l in lines if l.strip()]
    if len(non_empty_lines) >= 6:
        unique_lines = set(non_empty_lines)
        repetition_ratio = 1.0 - (len(unique_lines) / len(non_empty_lines))
        if repetition_ratio > 0.40:
            return 0.2, False

    # Rule 5: Boilerplate line ratio
    bp_lines = sum(
        1 for line in non_empty_lines
        if any(token in line for token in _BOILERPLATE_TOKENS)
    )
    if len(non_empty_lines) and (bp_lines / len(non_empty_lines)) > 0.35:
        return 0.3, False

    # Calculate fine-grained continuous quality score (0.5 to 1.0)
    score = 0.60
    # Length bonus (up to +0.20)
    score += min(0.20, (total_words / 1000.0) * 0.20)
    # Stopword normality bonus (+0.10)
    if 0.28 <= stopword_ratio <= 0.60:
        score += 0.10
    # Clean symbol bonus (+0.10)
    if symbol_ratio < 0.05:
        score += 0.10

    return min(1.0, round(score, 3)), True


def quality_filter(documents: list[dict[str, Any]], min_text_length: int = 200) -> list[dict[str, Any]]:
    kept = []
    for doc in documents:
        raw_text = doc.get("text") or ""
        text = normalize_text(raw_text)
        doc["text"] = text

        if len(text) < min_text_length:
            continue

        words = re.findall(r"\w+", text)
        lines = text.splitlines()

        score, acceptable = calculate_quality_score(text, words, lines)
        if not acceptable:
            continue

        doc["quality_score"] = score
        kept.append(doc)

    return kept
