from __future__ import annotations

import asyncio
import json
import queue
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from loomset.labeling.ollama_client import check_ollama_status, _get_client
from loomset.pipeline import run_pipeline, status_summary

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / "index.html"
DATA_DIR = ROOT / "data"
EXPORTS_DIR = DATA_DIR / "exports"

app = FastAPI(title="LoomSet", version="0.1.0")

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve exported dataset files (entire exports tree)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/files", StaticFiles(directory=str(EXPORTS_DIR)), name="exports")


def _download_tokens(query_slug: str) -> dict[str, str]:
    """Return per-format download URL tokens for the given query slug."""
    return {
        "json": f"{query_slug}/dataset.json",
        "csv": f"{query_slug}/dataset.csv",
        "parquet": f"{query_slug}/dataset.parquet",
    }


class RunRequest(BaseModel):
    query: str = Field(..., min_length=1)
    max_results: int = 10
    db_path: str | None = None
    export_dir: str | None = None
    data_dir: str | None = None
    labels: list[str] | None = None
    model: str | None = None


@app.get("/")
def serve_index() -> FileResponse:
    return FileResponse(INDEX_PATH)


@app.get("/index.html")
def serve_index_alias() -> FileResponse:
    return FileResponse(INDEX_PATH)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"ok": True, "service": "loomset"}


@app.get("/api/ollama/status")
def ollama_status() -> dict[str, object]:
    result = check_ollama_status()
    return {"ok": True, **result}


@app.get("/api/status")
def api_status(query: str | None = None) -> dict[str, object]:
    db_path = DATA_DIR / "loomset.db"
    if not db_path.exists():
        return {"ok": True, "summary": {}}
    summary = status_summary(str(db_path), query=query)
    return {"ok": True, "summary": summary}


@app.get("/api/dataset")
def api_dataset(path: str | None = None, query: str | None = None) -> dict[str, object]:
    target = None
    if path:
        target = Path(path)
    elif query:
        from loomset.pipeline import _query_slug
        candidate = EXPORTS_DIR / _query_slug(query) / "dataset.json"
        if candidate.exists():
            target = candidate
    if target is None:
        target = EXPORTS_DIR / "dataset.json"
    if not target.exists():
        raise HTTPException(status_code=404, detail="Dataset not found")
    content = target.read_text(encoding="utf-8").strip()
    if not content:
        return {"ok": True, "records": [], "path": str(target)}
    try:
        payload = json.loads(content)
        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict) and "records" in payload:
            records = payload["records"]
        else:
            records = [payload]
    except Exception:
        records = [json.loads(line) for line in content.splitlines() if line.strip()]
    if query:
        records = [r for r in records if not r.get("query") or query.lower() in r.get("query", "").lower()]
    return {"ok": True, "records": records[:25], "path": str(target)}


@app.get("/api/download/{filepath:path}")
def download_file(filepath: str) -> FileResponse:
    # Resolve safely inside EXPORTS_DIR (prevent path traversal)
    safe = (EXPORTS_DIR / filepath).resolve()
    if not str(safe).startswith(str(EXPORTS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not safe.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filepath}")
    return FileResponse(safe, filename=safe.name)


@app.post("/api/run")
def api_run(request: RunRequest) -> dict[str, object]:
    if request.model:
        _get_client(model=request.model)
    try:
        result = run_pipeline(
            query=request.query,
            max_results=request.max_results,
            db_path=request.db_path,
            export_dir=request.export_dir,
            data_dir=request.data_dir,
            labels=request.labels,
        )
    except Exception as exc:  # pragma: no cover - defensive API guard
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    slug = result.get("query_slug", "dataset")
    tokens = _download_tokens(slug)
    return {
        "ok": True,
        "records": result["records"],
        "query_slug": slug,
        "download": tokens,
        "dataset_path": str(result["dataset_path"]),
        "csv_path": str(result["csv_path"]),
        "parquet_path": str(result["parquet_path"]),
        "card_path": str(result["card_path"]),
        "count": len(result["records"]),
    }


@app.post("/api/run/stream")
async def api_run_stream(request: RunRequest) -> StreamingResponse:
    """Run the pipeline and stream progress events via SSE."""
    if request.model:
        _get_client(model=request.model)
    event_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def progress_callback(event: dict[str, Any]) -> None:
        event_queue.put(event)

    def run_in_thread() -> None:
        try:
            result = run_pipeline(
                query=request.query,
                max_results=request.max_results,
                db_path=request.db_path,
                export_dir=request.export_dir,
                data_dir=request.data_dir,
                labels=request.labels,
                callback=progress_callback,
            )
            # Emit final result event
            slug = result.get("query_slug", "dataset")
            tokens = _download_tokens(slug)
            event_queue.put({
                "stage": "result",
                "status": "complete",
                "records": result["records"],
                "query_slug": slug,
                "download": tokens,
                "dataset_path": str(result["dataset_path"]),
                "csv_path": str(result["csv_path"]),
                "parquet_path": str(result["parquet_path"]),
                "card_path": str(result["card_path"]),
                "count": len(result["records"]),
            })
        except Exception as exc:
            event_queue.put({"stage": "error", "status": "failed", "message": str(exc)})
        finally:
            event_queue.put(None)  # sentinel to end the stream

    # Start pipeline in background thread
    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()

    async def event_generator():
        while True:
            try:
                # Poll the queue with a short timeout to allow async cancellation
                event = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: event_queue.get(timeout=0.5)
                )
                if event is None:
                    # Send final close event
                    yield f"data: {json.dumps({'stage': 'done', 'status': 'closed'})}\n\n"
                    break
                yield f"data: {json.dumps(event, default=str)}\n\n"
            except queue.Empty:
                # Send keepalive
                yield f": keepalive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("loomset.server:app", host="0.0.0.0", port=8000, reload=True)
