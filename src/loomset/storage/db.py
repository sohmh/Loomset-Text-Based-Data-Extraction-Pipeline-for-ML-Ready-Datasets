from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse, urlunparse
from uuid import uuid4


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    query TEXT,
    domain TEXT,
    fetch_method TEXT,
    raw_html TEXT,
    fetched_at TEXT,
    status TEXT DEFAULT 'discovered'
);

CREATE TABLE IF NOT EXISTS extracted_text (
    doc_id TEXT PRIMARY KEY,
    title TEXT,
    text TEXT,
    lang TEXT,
    extracted_at TEXT
);

CREATE TABLE IF NOT EXISTS cleaned_text (
    doc_id TEXT PRIMARY KEY,
    text TEXT,
    dedup_hash TEXT,
    quality_score REAL,
    cleaned_at TEXT
);

CREATE TABLE IF NOT EXISTS labels (
    doc_id TEXT PRIMARY KEY,
    label TEXT,
    label_source TEXT,
    confidence REAL,
    reviewed BOOLEAN DEFAULT 0,
    labeled_at TEXT
);
"""


def ensure_db(path: str | Path):
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate_document_urls(conn)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_url ON documents(url)")
        conn.commit()


@contextmanager
def get_connection(path: str | Path) -> Iterator[sqlite3.Connection]:
    ensure_db(path)
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()


def fetch_documents(path: str | Path, status: str | None = None, limit: int | None = None, query: str | None = None) -> list[dict[str, Any]]:
    with get_connection(path) as conn:
        sql = "SELECT * FROM documents WHERE 1=1"
        params: list[Any] = []
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        if query is not None:
            sql += " AND LOWER(query) = LOWER(?)"
            params.append(query)
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def fetch_extracted_text(path: str | Path, doc_id: str | None = None) -> list[dict[str, Any]]:
    with get_connection(path) as conn:
        query = "SELECT * FROM extracted_text"
        params: list[Any] = []
        if doc_id is not None:
            query += " WHERE doc_id = ?"
            params.append(doc_id)
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def fetch_cleaned_text(path: str | Path, doc_id: str | None = None) -> list[dict[str, Any]]:
    with get_connection(path) as conn:
        query = "SELECT * FROM cleaned_text"
        params: list[Any] = []
        if doc_id is not None:
            query += " WHERE doc_id = ?"
            params.append(doc_id)
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def fetch_labels(path: str | Path, doc_id: str | None = None) -> list[dict[str, Any]]:
    with get_connection(path) as conn:
        query = "SELECT * FROM labels"
        params: list[Any] = []
        if doc_id is not None:
            query += " WHERE doc_id = ?"
            params.append(doc_id)
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def _migrate_document_urls(conn: sqlite3.Connection) -> None:
    """Canonicalize legacy rows and merge duplicate URLs before indexing them."""
    rows = conn.execute("SELECT id, url FROM documents ORDER BY rowid").fetchall()
    retained: dict[str, str] = {}
    for doc_id, url in rows:
        canonical = normalize_url(url)
        keeper = retained.get(canonical)
        if keeper is None:
            retained[canonical] = doc_id
            conn.execute("UPDATE documents SET url = ? WHERE id = ?", (canonical, doc_id))
            continue
        for table in ("extracted_text", "cleaned_text", "labels"):
            conn.execute(f"UPDATE OR REPLACE {table} SET doc_id = ? WHERE doc_id = ?", (keeper, doc_id))
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = hostname
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def upsert_document(path: str | Path, record: dict[str, Any]) -> bool:
    """Insert a document or merge a rediscovered URL without resetting progress.

    Returns True only when a new URL is inserted. A discovery record never moves an
    existing document backwards, which makes repeated runs incremental and resumable.
    """
    record = {**record, "url": normalize_url(record["url"])}
    with get_connection(path) as conn:
        existing = conn.execute("SELECT * FROM documents WHERE url = ?", (record["url"],)).fetchone()
        if existing is None:
            columns = ["id", "url", "query", "domain", "fetch_method", "raw_html", "fetched_at", "status"]
            record = {**record, "id": record.get("id") or str(uuid4())}
            conn.execute(
                f"INSERT INTO documents ({', '.join(columns)}) VALUES ({', '.join(['?'] * len(columns))})",
                [record.get(col) for col in columns],
            )
            conn.commit()
            return True

        current = dict(existing)
        incoming_status = record.get("status")
        updates = {
            key: value
            for key, value in record.items()
            if key in {"query", "domain", "fetch_method", "raw_html", "fetched_at"} and value is not None
        }
        if incoming_status and incoming_status != "discovered":
            updates["status"] = incoming_status
        elif current.get("status") == "discovered":
            updates["status"] = "discovered"
        if updates:
            assignments = ", ".join(f"{key} = ?" for key in updates)
            conn.execute(
                f"UPDATE documents SET {assignments} WHERE url = ?",
                [*updates.values(), record["url"]],
            )
        conn.commit()
        return False


def update_document_status(path: str | Path, doc_id: str, status: str, fetch_method: str | None = None, raw_html: str | None = None) -> None:
    with get_connection(path) as conn:
        if fetch_method is not None:
            conn.execute(
                "UPDATE documents SET status = ?, fetch_method = ?, raw_html = ? WHERE id = ?",
                (status, fetch_method, raw_html, doc_id),
            )
        else:
            conn.execute("UPDATE documents SET status = ? WHERE id = ?", (status, doc_id))
        conn.commit()


def insert_extracted_text(path: str | Path, doc_id: str, title: str | None, text: str | None, lang: str | None, extracted_at: str) -> None:
    with get_connection(path) as conn:
        conn.execute(
            "INSERT INTO extracted_text (doc_id, title, text, lang, extracted_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(doc_id) DO UPDATE SET title=excluded.title, text=excluded.text, lang=excluded.lang, extracted_at=excluded.extracted_at",
            (doc_id, title, text, lang, extracted_at),
        )
        conn.commit()


def insert_cleaned_text(path: str | Path, doc_id: str, text: str, dedup_hash: str, quality_score: float, cleaned_at: str) -> None:
    with get_connection(path) as conn:
        conn.execute(
            "INSERT INTO cleaned_text (doc_id, text, dedup_hash, quality_score, cleaned_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(doc_id) DO UPDATE SET text=excluded.text, dedup_hash=excluded.dedup_hash, quality_score=excluded.quality_score, cleaned_at=excluded.cleaned_at",
            (doc_id, text, dedup_hash, quality_score, cleaned_at),
        )
        conn.commit()


def insert_label(path: str | Path, doc_id: str, label: str, label_source: str, confidence: float, reviewed: bool, labeled_at: str) -> None:
    with get_connection(path) as conn:
        conn.execute(
            "INSERT INTO labels (doc_id, label, label_source, confidence, reviewed, labeled_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(doc_id) DO UPDATE SET label=excluded.label, label_source=excluded.label_source, confidence=excluded.confidence, reviewed=excluded.reviewed, labeled_at=excluded.labeled_at",
            (doc_id, label, label_source, confidence, int(reviewed), labeled_at),
        )
        conn.commit()


def update_status(path: str | Path, doc_id: str, status: str) -> None:
    with get_connection(path) as conn:
        conn.execute("UPDATE documents SET status = ? WHERE id = ?", (status, doc_id))
        conn.commit()
