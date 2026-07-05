"""Central path computation for all memory artifacts.

New unified structure::

    memory/
    └── YYYY/
        └── MM/
            └── DD/
                ├── session--{channel}--{id}.md
                ├── transversal.md
                ├── daily.md
                ├── inbox.jsonl
                ├── recall.jsonl
                ├── morning-plan.md
                ├── candidates/
                │   ├── session_summary.jsonl
                │   ├── transversal_synthesis.jsonl
                │   ├── tracer.jsonl
                │   └── recall_links.jsonl
                └── events/
                    ├── curation.md
                    └── decisions.jsonl

All functions accept a *target* (date, string, or None for today/yesterday)
and an optional *root* (project root, auto-detected if None).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Union


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    """Return the project root (3 levels up from src/memory/paths.py)."""
    return Path(__file__).resolve().parents[2]


def _default_target_date(now: datetime | None = None) -> date:
    current = now or datetime.now()
    if current.hour < 4:
        return (current - timedelta(days=1)).date()
    return current.date()


def _normalize_target(target: Union[date, str, None] = None) -> str:
    if target is None:
        target = _default_target_date()
    return target.isoformat() if isinstance(target, date) else str(target)


def _resolve_root(root: str | Path | None = None) -> Path:
    return Path(root) if root is not None else _project_root()


# ---------------------------------------------------------------------------
# Base date directory  —  memory/YYYY/MM/DD/
# ---------------------------------------------------------------------------

def date_dir(target: Union[date, str, None] = None,
             root: str | Path | None = None) -> Path:
    """Return ``memory/YYYY/MM/DD``."""
    date_str = _normalize_target(target)
    y, m, d = date_str.split("-")
    return _resolve_root(root) / "memory" / y / m / d


# ---------------------------------------------------------------------------
# Single-artifact paths  (one per day)
# ---------------------------------------------------------------------------

def session_summary_path(session_id: str,
                          channel: str = "web",
                          target: Union[date, str, None] = None,
                          root: str | Path | None = None) -> Path:
    """``session--{channel}--{id_prefix}.md`` inside the date directory."""
    safe_ch = re.sub(r"[^A-Za-z0-9_.-]+", "_", channel or "web").strip("_") or "web"
    safe_sid = re.sub(r"[^A-Za-z0-9_.-]+", "_", session_id).strip("_") or "session"
    short = safe_sid[:12]
    return date_dir(target, root) / f"session--{safe_ch}--{short}.md"


def transversal_path(target: Union[date, str, None] = None,
                     root: str | Path | None = None) -> Path:
    """``transversal.md`` inside the date directory."""
    return date_dir(target, root) / "transversal.md"


def daily_path(target: Union[date, str, None] = None,
               root: str | Path | None = None) -> Path:
    """``daily.md`` inside the date directory."""
    return date_dir(target, root) / "daily.md"


def inbox_path(target: Union[date, str, None] = None,
               root: str | Path | None = None) -> Path:
    """``inbox.jsonl`` inside the date directory."""
    return date_dir(target, root) / "inbox.jsonl"


def recall_events_path(target: Union[date, str, None] = None,
                        root: str | Path | None = None) -> Path:
    """``recall.jsonl`` inside the date directory."""
    return date_dir(target, root) / "recall.jsonl"


def morning_plan_path(target: Union[date, str, None] = None,
                       root: str | Path | None = None) -> Path:
    """``morning-plan.md`` inside the date directory."""
    return date_dir(target, root) / "morning-plan.md"


# ---------------------------------------------------------------------------
# Candidate paths  (multiple per day → subfolder)
# ---------------------------------------------------------------------------

def candidate_path(kind: str,
                   target: Union[date, str, None] = None,
                   root: str | Path | None = None) -> Path:
    """``candidates/{kind}.jsonl`` inside the date directory."""
    return date_dir(target, root) / "candidates" / f"{kind}.jsonl"


def session_summary_candidate_path(target: Union[date, str, None] = None,
                                    root: str | Path | None = None) -> Path:
    """Candidates derived from session summaries."""
    return candidate_path("session_summary", target, root)


def transversal_candidate_path(target: Union[date, str, None] = None,
                                root: str | Path | None = None) -> Path:
    """Candidates derived from transversal synthesis."""
    return candidate_path("transversal_synthesis", target, root)


def tracer_candidate_path(target: Union[date, str, None] = None,
                           root: str | Path | None = None) -> Path:
    """Candidates from the tracer."""
    return candidate_path("tracer", target, root)


def recall_candidate_path(target: Union[date, str, None] = None,
                           root: str | Path | None = None) -> Path:
    """Candidates from recall links."""
    return candidate_path("recall_links", target, root)


# ---------------------------------------------------------------------------
# Event paths  (multiple per day → subfolder)
# ---------------------------------------------------------------------------

def event_path(kind: str,
               target: Union[date, str, None] = None,
               root: str | Path | None = None) -> Path:
    """``events/{kind}`` inside the date directory."""
    return date_dir(target, root) / "events" / kind


def curation_report_path(target: Union[date, str, None] = None,
                          root: str | Path | None = None) -> Path:
    """Curation run report (Markdown)."""
    return event_path("curation.md", target, root)


def curation_decision_path(target: Union[date, str, None] = None,
                            root: str | Path | None = None) -> Path:
    """Curation decisions (JSONL)."""
    return event_path("decisions.jsonl", target, root)
