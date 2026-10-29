from __future__ import annotations

import atexit
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("loomset.ollama_manager")

_SPAWNED_PROCESS: subprocess.Popen | None = None


def find_ollama_executable() -> str | None:
    """Locate the ollama executable on the system."""
    # 1. Check system PATH
    bin_path = shutil.which("ollama")
    if bin_path and os.path.exists(bin_path):
        return bin_path

    # 2. Check standard Windows locations
    local_appdata = os.environ.get("LOCALAPPDATA")
    candidates = []
    if local_appdata:
        candidates.append(Path(local_appdata) / "Programs" / "Ollama" / "ollama.exe")
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidates.append(Path(program_files) / "Ollama" / "ollama.exe")

    # Common Unix locations
    candidates.extend([
        Path("/usr/local/bin/ollama"),
        Path("/usr/bin/ollama"),
        Path.home() / ".local" / "bin" / "ollama",
    ])

    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)

    return None


def is_ollama_running(base_url: str = "http://localhost:11434", timeout: float = 1.5) -> bool:
    """Check if the Ollama HTTP server is responsive."""
    try:
        resp = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def start_ollama_server(
    base_url: str = "http://localhost:11434",
    timeout: float = 15.0,
) -> bool:
    """Start `ollama serve` if it is not already running.

    Returns True if the server is running (either previously or newly started).
    """
    global _SPAWNED_PROCESS

    if is_ollama_running(base_url=base_url):
        logger.info("Ollama is already running at %s", base_url)
        return True

    ollama_bin = find_ollama_executable()
    if not ollama_bin:
        logger.warning("Ollama executable not found on the system. Local LLM auto-start skipped.")
        return False

    logger.info("Starting Ollama daemon: %s serve", ollama_bin)
    try:
        creationflags = 0
        if os.name == "nt":
            # CREATE_NO_WINDOW or CREATE_NEW_PROCESS_GROUP
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        _SPAWNED_PROCESS = subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except Exception as exc:
        logger.error("Failed to launch ollama serve: %s", exc)
        return False

    # Poll until ready
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_ollama_running(base_url=base_url, timeout=0.8):
            logger.info("Ollama daemon started successfully and responsive at %s", base_url)
            return True
        time.sleep(0.5)

    logger.warning("Timed out waiting for Ollama to become responsive after %.1fs", timeout)
    return False


def stop_ollama_server() -> None:
    """Gracefully terminate the Ollama daemon if it was spawned by LoomSet."""
    global _SPAWNED_PROCESS
    if _SPAWNED_PROCESS is not None:
        try:
            logger.info("Stopping LoomSet-managed Ollama daemon (PID %d)...", _SPAWNED_PROCESS.pid)
            _SPAWNED_PROCESS.terminate()
            try:
                _SPAWNED_PROCESS.wait(timeout=3)
            except subprocess.TimeoutExpired:
                _SPAWNED_PROCESS.kill()
        except Exception as exc:
            logger.warning("Error stopping Ollama process: %s", exc)
        finally:
            _SPAWNED_PROCESS = None


# Automatically clean up spawned daemon on interpreter exit
atexit.register(stop_ollama_server)


def get_available_models(base_url: str = "http://localhost:11434") -> list[str]:
    """Return a list of model tags available in the running Ollama instance."""
    try:
        resp = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=3.0)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            return [m.get("name", "") for m in models if m.get("name")]
    except Exception:
        pass
    return []


def resolve_best_model(
    preferred_model: str = "",
    base_url: str = "http://localhost:11434",
) -> str:
    """Return the preferred model if installed, or the best available alternative."""
    models = get_available_models(base_url=base_url)
    if not models:
        return ""

    if preferred_model:
        # Check exact or prefix match
        pref_lower = preferred_model.lower()
        for m in models:
            if m.lower() == pref_lower or m.lower().startswith(pref_lower):
                return m

    # Ranked preferences for popular coding/classification models
    priority = [
        "qwen3:8b", "qwen3", "qwen2.5:7b", "qwen2.5:3b", "qwen2.5",
        "llama3.2:3b", "llama3.2:1b", "llama3.2", "llama3.1:8b", "llama3.1", "llama3:8b",
        "mistral:latest", "mistral:7b", "mistral",
        "phi3:mini", "phi3", "gemma2:9b", "gemma2:2b", "gemma2",
    ]
    for pref in priority:
        for m in models:
            if pref in m.lower():
                return m

    return models[0]

