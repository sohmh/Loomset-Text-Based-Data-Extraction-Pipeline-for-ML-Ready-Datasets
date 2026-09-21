from __future__ import annotations

from pathlib import Path
from typing import Any


import json


def export_review_batch(records: list[dict[str, Any]], output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "id": r["id"],
            "data": {
                "text": r.get("text", ""),
                "label": r.get("label", ""),
                "url": r.get("url", ""),
            },
        }
        for r in records
    ]
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
