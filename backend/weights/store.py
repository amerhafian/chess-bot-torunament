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


def _normalize_saved(data: dict[str, Any], weight_id: str) -> dict[str, Any]:
    """Ensure saved payloads expose power-form keys plus legacy a/b/c."""
    weights = Weights.from_dict(data)
    payload = {
        "id": weight_id,
        "name": data.get("name", weight_id),
        **weights.to_dict(),
        "source": data.get("source"),
        "bot_name": data.get("bot_name"),
        "created_at": data.get("created_at", 0),
    }
    return payload


def list_weights() -> list[dict[str, Any]]:
    _ensure_dir()
    items: list[dict[str, Any]] = []
    for path in sorted(WEIGHTS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items.append(_normalize_saved(data, data.get("id", path.stem)))
        except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
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
        return _normalize_saved(data, weight_id)
    except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
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
        **weights.to_dict(),
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
