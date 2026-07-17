"""Pure helpers for layered memory health contracts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def health_status_semantics() -> dict[str, str]:
    """Return the stable meaning of each public health status."""

    return {
        "error": "blocking technical integrity failure; automated success must not be reported",
        "attention": "non-blocking operational coverage gap that needs explicit follow-up",
        "warning": "non-blocking curated quality signal, including historical debt",
        "ok": "no findings in the evaluated dimension",
    }


def normalize_health_status(value: object, *, legacy_ok: object = None) -> str:
    """Normalize layered status while accepting the legacy boolean contract."""

    status = str(value or "").strip().lower()
    if status in {"error", "attention", "warning", "ok"}:
        return status
    if legacy_ok is False:
        return "error"
    return "ok"


def worst_health_status(statuses: Iterable[object]) -> str:
    """Return the most severe status from an iterable."""

    normalized = [normalize_health_status(status) for status in statuses]
    if "error" in normalized:
        return "error"
    if "attention" in normalized:
        return "attention"
    if "warning" in normalized:
        return "warning"
    return "ok"


def health_dimension(
    *,
    finding_status: str,
    findings: list[dict[str, Any]],
    metrics: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one dimension with machine-readable findings and legacy-friendly text."""

    status = normalize_health_status(finding_status) if findings else "ok"
    return {
        "status": status,
        "ok": not findings,
        "findings": findings,
        "issues": [str(item.get("message") or item.get("code") or "") for item in findings],
        "metrics": dict(metrics),
    }
