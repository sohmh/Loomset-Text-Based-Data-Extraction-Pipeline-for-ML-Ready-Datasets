from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

logger = logging.getLogger("loomset.labeling")


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = ""):
        self.base_url = base_url.rstrip("/")
        self.model = model or self._detect_model()

    def _detect_model(self) -> str:
        """Auto-detect the best available model from Ollama."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            models = response.json().get("models", [])
            if models:
                model_names = [m.get("name", "") for m in models]
                # Check preferred models first
                preferred = ["qwen3:8b", "qwen3", "llama3.2:3b", "llama3.2", "mistral:latest", "mistral"]
                for pref in preferred:
                    for name in model_names:
                        if pref in name.lower():
                            logger.info("Auto-detected preferred Ollama model: %s", name)
                            return name
                name = model_names[0]
                logger.info("Auto-detected Ollama model: %s", name)
                return name
        except Exception:
            pass
        return ""

    def is_available(self) -> bool:
        """Check if Ollama is reachable and has at least one model."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            models = response.json().get("models", [])
            return len(models) > 0
        except Exception:
            return False

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
                text = data.get("response", "")
                return json.loads(text)
            except Exception as exc:
                last_error = exc
                if attempt < retries:
                    wait = 2 ** attempt
                    logger.warning("Ollama attempt %d failed, retrying in %ds: %s", attempt + 1, wait, exc)
                    time.sleep(wait)

        raise last_error or RuntimeError("Ollama generation failed")


def _keyword_fallback(text: str, query: str, allowed_labels: list[str]) -> dict[str, Any]:
    """Simple keyword-matching fallback when Ollama is unavailable."""
    text_lower = text.lower()
    query_lower = query.lower()
    query_words = [w.strip() for w in query_lower.split() if len(w.strip()) > 2]

    matches = sum(1 for word in query_words if word in text_lower)
    ratio = matches / max(len(query_words), 1)

    if ratio >= 0.3:
        label = "relevant" if "relevant" in allowed_labels else allowed_labels[0]
        confidence = min(0.85, 0.5 + ratio * 0.5)
    else:
        label = "irrelevant" if "irrelevant" in allowed_labels else allowed_labels[-1]
        confidence = min(0.75, 0.4 + (1 - ratio) * 0.3)

    return {"label": label, "confidence": round(confidence, 3)}


# Module-level client instance, lazily initialized
_client: OllamaClient | None = None


def _get_client(base_url: str = "http://localhost:11434", model: str = "") -> OllamaClient:
    global _client
    if _client is None:
        _client = OllamaClient(base_url=base_url, model=model)
    else:
        if model and _client.model != model:
            _client.model = model
        elif not _client.model:
            _client.model = _client._detect_model()
    return _client


def check_ollama_status(base_url: str = "http://localhost:11434") -> dict[str, Any]:
    """Return Ollama availability status for the API."""
    try:
        response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=5)
        response.raise_for_status()
        models = response.json().get("models", [])
        model_names = [m.get("name", "") for m in models]
        client = _get_client(base_url=base_url)
        active_model = client.model or (model_names[0] if model_names else "")
        return {"available": len(models) > 0, "models": model_names, "active_model": active_model}
    except Exception:
        return {"available": False, "models": [], "active_model": ""}


def auto_label_text(text: str, query: str, allowed_labels: list[str] | None = None, base_url: str = "http://localhost:11434", model: str = "") -> dict[str, Any]:
    allowed = allowed_labels or ["relevant", "irrelevant"]

    client = _get_client(base_url=base_url, model=model)

    if not client.model:
        logger.info("No Ollama model available, using keyword fallback")
        return _keyword_fallback(text, query, allowed)

    # Truncate very long texts to avoid timeout
    text_snippet = text[:3000] if len(text) > 3000 else text

    prompt = (
        "You are a strict classifier. Decide whether the text is relevant to the query. "
        f"Query: {query}\n"
        "Return ONLY a JSON object with keys: label and confidence. "
        f"Allowed labels: {allowed}. "
        "Confidence must be between 0 and 1.\n"
        f"Text:\n{text_snippet}"
    )

    try:
        result = client.generate(prompt)
        if result.get("label") not in allowed:
            result["label"] = allowed[0] if query.lower() in text.lower() else allowed[-1]
        conf = float(result.get("confidence", 0.5))
        if not 0.0 <= conf <= 1.0:
            conf = 0.5
        return {"label": result["label"], "confidence": conf}
    except Exception as exc:
        logger.warning("Ollama labeling failed, using keyword fallback: %s", exc)
        return _keyword_fallback(text, query, allowed)
