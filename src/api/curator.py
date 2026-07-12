"""Curator review facade for the web layer.

The web application consumes curator data through this module so that
framework-facing routers do not import ``src.memory`` directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_curator_candidates(
    root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Load reviewable curator candidates from the memory artifact store."""

    from src.memory.curator.candidate_workbench import load_candidate_records

    return load_candidate_records(root=root or _project_root())


def build_curator_candidate_card(record: dict[str, Any]) -> dict[str, Any]:
    """Build the presentation-neutral card for one curator candidate."""

    from src.memory.curator.candidate_workbench import candidate_card

    return candidate_card(record)


def load_curator_decisions(
    root: str | Path | None = None,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Load recent curator decisions from the memory artifact store."""

    from src.memory.curator.curation_events import load_curation_decisions

    return load_curation_decisions(root=root or _project_root(), limit=limit)


def append_curator_decision(
    event: dict[str, Any],
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Persist one curator decision through the domain facade."""

    from src.memory.curator.curation_events import append_curation_decision

    return append_curation_decision(event, root=root or _project_root())


__all__ = [
    "append_curator_decision",
    "build_curator_candidate_card",
    "load_curator_candidates",
    "load_curator_decisions",
]
