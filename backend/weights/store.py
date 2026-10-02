"""JSON persistence for evaluation weight presets."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Optional

from backend.engine.evaluation import Weights
from backend.tournament.models import new_id

WEIGHTS_DIR = Path(__file__).resolve().parents[2] / "data" / "weights"


def _ensure_dir() -> None:
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip())[:64]
    return cleaned or "weights"


def list_weights() -> list[dict[str, Any]]:
    _ensure_dir()
    items: list[dict[str, Any]] = []
    for path in sorted(WEIGHTS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data.setdefault("id", path.stem)
            items.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    items.sort(key=lambda d: d.get("created_at", 0), reverse=True)
    return items


def get_weights(weight_id: str) -> Optional[dict[str, Any]]:
    _ensure_dir()
    path = WEIGHTS_DIR / f"{weight_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("id", weight_id)
        return data
    except (json.JSONDecodeError, OSError):
        return None


def save_weights(
    name: str,
    weights: Weights,
    *,
    source: Optional[str] = None,
    bot_name: Optional[str] = None,
    weight_id: Optional[str] = None,
) -> dict[str, Any]:
    _ensure_dir()
    wid = weight_id or f"{_safe_filename(name)}_{new_id()}"
    payload = {
        "id": wid,
        "name": name,
        "a": weights.material,
        "b": weights.controlled,
        "c": weights.checking,
        "source": source,
        "bot_name": bot_name,
        "created_at": time.time(),
    }
    path = WEIGHTS_DIR / f"{wid}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def delete_weights(weight_id: str) -> bool:
    _ensure_dir()
    path = WEIGHTS_DIR / f"{weight_id}.json"
    if not path.exists():
        return False
    path.unlink()
    return True
