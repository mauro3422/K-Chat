from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_MODEL_REGISTRY = Path.home() / ".local/share/opencode-delegate/model_registry.json"


def _registry_path() -> Path:
    override = os.environ.get("KAIROS_MODEL_REGISTRY") or os.environ.get("OPENCODE_MODEL_REGISTRY")
    if override:
        return Path(override).expanduser()
    return DEFAULT_MODEL_REGISTRY


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, dict[str, Any]]:
    path = _registry_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    models = data.get("models", [])
    catalog: dict[str, dict[str, Any]] = {}
    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not model_id:
            continue
        caps = item.get("capabilities", {}) if isinstance(item.get("capabilities"), dict) else {}
        limit = item.get("limit", {}) if isinstance(item.get("limit"), dict) else {}
        cost = item.get("cost", {}) if isinstance(item.get("cost"), dict) else {}
        catalog[str(model_id)] = {
            "id": str(model_id),
            "name": item.get("name") or str(model_id),
            "context": limit.get("context"),
            "output": limit.get("output"),
            "image": bool((caps.get("input") or {}).get("image")) if isinstance(caps.get("input"), dict) else False,
            "audio": bool((caps.get("input") or {}).get("audio")) if isinstance(caps.get("input"), dict) else False,
            "video": bool((caps.get("input") or {}).get("video")) if isinstance(caps.get("input"), dict) else False,
            "attachment": bool(caps.get("attachment")),
            "reasoning": bool(caps.get("reasoning")),
            "toolcall": bool(caps.get("toolcall")),
            "temperature": bool(caps.get("temperature")),
            "cost_input": cost.get("input"),
            "cost_output": cost.get("output"),
            "release_date": item.get("release_date"),
            "status": item.get("status"),
        }
    return catalog


def get_model_metadata(model_id: str) -> dict[str, Any] | None:
    return _load_registry().get(model_id)


def _compact_ctx(value: Any) -> str | None:
    if not isinstance(value, int) or value <= 0:
        return None
    if value >= 1_000_000:
        return f"{value // 1_000_000}M"
    if value >= 1_000:
        return f"{value // 1_000}k"
    return str(value)


def _modality_label(meta: dict[str, Any]) -> str:
    modalities = []
    if meta.get("image"):
        modalities.append("img")
    if meta.get("audio"):
        modalities.append("audio")
    if meta.get("video"):
        modalities.append("video")
    if not modalities:
        modalities.append("texto")
    return "+".join(modalities)


def invalidate_model_cache() -> None:
    _load_registry.cache_clear()


def reset_model_cache() -> None:
    """Alias for invalidate_model_cache() to match lifecycle helpers."""
    invalidate_model_cache()


def format_model_label(model_id: str) -> str:
    meta = get_model_metadata(model_id)
    if not meta:
        return model_id

    bits = []
    ctx = _compact_ctx(meta.get("context"))
    if ctx:
        bits.append(f"ctx {ctx}")
    out = _compact_ctx(meta.get("output"))
    if out:
        bits.append(f"out {out}")
    bits.append(_modality_label(meta))
    if meta.get("reasoning"):
        bits.append("razonamiento")
    if meta.get("toolcall"):
        bits.append("tools")
    return f"{meta.get('name') or model_id} · " + " · ".join(bits)
