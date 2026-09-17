"""Small, best-effort disk cache for validated Gemini responses."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


CACHE_DIR = Path(".cache")
CACHE_TTL_SECONDS = 24 * 60 * 60


def _cache_path(feature: str, context: Any) -> Path:
    encoded = json.dumps(context, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{feature}-{digest}.json"


def read(feature: str, context: Any, *, now: float | None = None) -> Any | None:
    """Return a fresh cached value, or None when it is missing/invalid/expired."""
    path = _cache_path(feature, context)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        created_at = float(payload["created_at"])
        if (time.time() if now is None else now) - created_at > CACHE_TTL_SECONDS:
            return None
        return payload["value"]
    except (OSError, ValueError, TypeError, KeyError):
        return None


def write(feature: str, context: Any, value: Any, *, now: float | None = None) -> None:
    """Persist a successful response without making cache failures fatal."""
    path = _cache_path(feature, context)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"created_at": time.time() if now is None else now, "value": value},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError):
        return
