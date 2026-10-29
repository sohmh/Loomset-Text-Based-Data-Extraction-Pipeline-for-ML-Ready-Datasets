from __future__ import annotations

import json
import logging
import math
import re
import time
from typing import Any

import requests

from loomset.labeling.ollama_manager import (
    get_available_models,
    is_ollama_running,
    resolve_best_model,
    start_ollama_server,
)

logger = logging.getLogger("loomset.labeling")


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "", auto_start: bool = True):
        self.base_url = base_url.rstrip("/")
        if auto_start and not is_ollama_running(base_url=self.base_url):
            start_ollama_server(base_url=self.base_url)
        self.model = model or self._detect_model()

    def _detect_model(self) -> str:
        """Auto-detect the best available model from Ollama."""
        return resolve_best_model(preferred_model="", base_url=self.base_url)

    def is_available(self) -> bool:
        """Check if Ollama is reachable and has at least one model."""
        models = get_available_models(base_url=self.base_url)
        return len(models) > 0

    def generate(self, prompt: str, timeout: int = 120, retries: int = 2) -> dict[str, Any]:
        if not self.model:
            raise RuntimeError("No Ollama model available")

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=timeout)
                response.raise_for_status()
                data = response.json()
                text = data.get("response", "").strip()
                # Parse JSON or extract first JSON object
                try:
                    return json.loads(text)
                except Exception:
                    match = re.search(r"\{.*?\}", text, re.DOTALL)
                    if match:
                        return json.loads(match.group(0))
                    raise ValueError(f"Could not parse JSON response from LLM: {text[:100]}")
            except Exception as exc:
                last_error = exc
                if attempt < retries:
                    wait = 2 ** attempt
                    logger.warning("Ollama attempt %d failed, retrying in %ds: %s", attempt + 1, wait, exc)
                    time.sleep(wait)

        raise last_error or RuntimeError("Ollama generation failed")


_STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "can", "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
    "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she",
    "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves",
    "then", "there", "these", "they", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom",
    "why", "with", "would", "you", "your", "yours", "yourself", "yourselves"
}


def _semantic_keyword_fallback(text: str, query: str, allowed_labels: list[str]) -> dict[str, Any]:
    """High-quality BM25-inspired keyword matching fallback when LLM is unavailable."""
    text_lower = text.lower()
    query_lower = query.lower()

    # Extract non-stopword query tokens
    raw_query_words = re.findall(r"[a-z0-9]+", query_lower)
    query_words = [w for w in raw_query_words if w not in _STOPWORDS and len(w) > 1]
    if not query_words:
        query_words = raw_query_words or [query_lower.strip()]

    # Check for exact query phrase match
    phrase_match = query_lower in text_lower

    # Token frequencies with sublinear scaling
    doc_words = re.findall(r"[a-z0-9]+", text_lower)
    doc_len = max(len(doc_words), 1)
    doc_freqs: dict[str, int] = {}
    for w in doc_words:
        doc_freqs[w] = doc_freqs.get(w, 0) + 1

    matched_weights = 0.0
    for qw in query_words:
        freq = doc_freqs.get(qw, 0)
        if freq > 0:
            # BM25-like saturation tf / (tf + 1.2)
            tf_score = (freq * 2.2) / (freq + 1.2 * (0.25 + 0.75 * (doc_len / 500.0)))
            matched_weights += min(1.0, tf_score)

    coverage_ratio = matched_weights / max(len(query_words), 1)

    # Determine relevance threshold
    if phrase_match or coverage_ratio >= 0.4:
        label = "relevant" if "relevant" in allowed_labels else allowed_labels[0]
        confidence = min(0.92, 0.60 + 0.35 * min(coverage_ratio, 1.0))
        if phrase_match:
            confidence = max(confidence, 0.85)
    else:
        label = "irrelevant" if "irrelevant" in allowed_labels else allowed_labels[-1]
        confidence = min(0.85, 0.50 + 0.35 * (1.0 - coverage_ratio))

    return {"label": label, "confidence": round(confidence, 3)}


# Module-level client instance, lazily initialized
_client: OllamaClient | None = None


def _get_client(base_url: str = "http://localhost:11434", model: str = "", auto_start: bool = False) -> OllamaClient:
    global _client
    if _client is None:
        _client = OllamaClient(base_url=base_url, model=model, auto_start=auto_start)
    else:
        if model and _client.model != model:
            _client.model = model
        elif not _client.model:
            _client.model = _client._detect_model()
    return _client


def check_ollama_status(base_url: str = "http://localhost:11434", auto_start: bool = False) -> dict[str, Any]:
    """Return Ollama availability status for the API, with optional auto-start."""
    if auto_start and not is_ollama_running(base_url=base_url):
        start_ollama_server(base_url=base_url, timeout=3.0)

    try:
        running = is_ollama_running(base_url=base_url, timeout=0.5)
        models = get_available_models(base_url=base_url) if running else []
        client = _get_client(base_url=base_url, auto_start=False)
        active_model = client.model or (models[0] if models else "")
        return {
            "available": len(models) > 0,
            "running": running,
            "models": models,
            "active_model": active_model,
        }
    except Exception:
        return {"available": False, "running": False, "models": [], "active_model": ""}


def auto_label_text(
    text: str,
    query: str,
    allowed_labels: list[str] | None = None,
    base_url: str = "http://localhost:11434",
    model: str = "",
) -> dict[str, Any]:
    allowed = allowed_labels or ["relevant", "irrelevant"]

    client = _get_client(base_url=base_url, model=model)

    if not client.model or not is_ollama_running(base_url=base_url):
        logger.info("Local Ollama model unavailable, using semantic fallback")
        return _semantic_keyword_fallback(text, query, allowed)

    # Use first 3500 characters
    text_snippet = text[:3500] if len(text) > 3500 else text

    prompt = (
        "You are an expert data curator and strict text classifier. "
        "Classify whether the given document is relevant to the topic query.\n\n"
        f"Topic Query: {query}\n"
        f"Allowed Labels: {allowed}\n\n"
        "Instructions:\n"
        "1. Read the document carefully.\n"
        "2. Choose exactly one label from the Allowed Labels list.\n"
        "3. Provide a confidence score between 0.00 and 1.00.\n"
        "4. Output ONLY valid JSON in this exact structure: "
        '{"reasoning": "brief explanation", "label": "...", "confidence": 0.95}\n\n'
        f"Document Content:\n{text_snippet}"
    )

    try:
        result = client.generate(prompt)
        assigned_label = result.get("label", "").strip()
        if assigned_label not in allowed:
            # Case-insensitive check
            for al in allowed:
                if al.lower() == assigned_label.lower():
                    assigned_label = al
                    break
            else:
                assigned_label = allowed[0] if query.lower() in text.lower() else allowed[-1]

        conf = float(result.get("confidence", 0.75))
        if not 0.0 <= conf <= 1.0:
            conf = 0.75

        return {
            "label": assigned_label,
            "confidence": round(conf, 3),
            "reasoning": result.get("reasoning", ""),
        }
    except Exception as exc:
        logger.warning("Ollama labeling failed, using semantic fallback: %s", exc)
        return _semantic_keyword_fallback(text, query, allowed)
