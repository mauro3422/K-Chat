"""Materialize and audit candidates emitted by conceptual synthesis."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


def candidate_id(candidate: dict[str, Any]) -> str:
    raw = f"{candidate.get('key', '')}|{candidate.get('value', '')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def discover_conceptual_candidates(root: str | Path) -> list[dict[str, Any]]:
    base = Path(root)
    records: list[dict[str, Any]] = []
    for path in sorted(base.glob("memory/*/*/*/conceptual.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        for raw in payload.get("memory_candidates", []):
            if not isinstance(raw, dict):
                continue
            item = {**raw, "source": "conceptual_synthesis", "source_artifact": str(path)}
            item["candidate_id"] = candidate_id(item)
            item["status"] = "pending"
            records.append(item)
    return records


def _tokens(text: str) -> set[str]:
    stop = {"para", "como", "with", "that", "this", "user", "usuario", "sistema", "memory", "memoria"}
    return {token for token in re.findall(r"[a-záéíóúñ0-9]{4,}", text.lower()) if token not in stop}


def audit_candidates(candidates: Iterable[dict[str, Any]], canonical_text: str) -> list[dict[str, Any]]:
    canon_tokens = _tokens(canonical_text)
    audited: list[dict[str, Any]] = []
    for candidate in candidates:
        tokens = _tokens(f"{candidate.get('key', '')} {candidate.get('value', '')}")
        overlap = len(tokens & canon_tokens) / max(len(tokens), 1)
        if overlap >= 0.75:
            state, risk = "duplicate_possible", "high"
        elif overlap >= 0.55:
            state, risk = "related_review", "medium"
        else:
            state, risk = "novel", "low"
        audited.append({**candidate, "canonical_overlap": round(overlap, 3), "audit_state": state, "audit_risk": risk, "promotion_decision": "review"})
    return audited


def write_candidate_dataset(path: str | Path, records: Iterable[dict[str, Any]]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return target
