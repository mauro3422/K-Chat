"""Curator review dashboard API used by the diagnostics page."""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from src.memory.curator.curation_events import append_curation_decision, load_curation_decisions
from src.memory.curator.candidate_workbench import candidate_card, load_candidate_records
from web.routers.debug import _trusted_lan_or_local


router = APIRouter(prefix="/api/diagnostics/curator")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _latest_quality_comparison() -> dict[str, Any]:
    directory = _project_root() / "test-results" / "curator-quality"
    paths = sorted(directory.glob("comparison-*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return {"file": str(path), **payload}
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def _candidate_cards(limit: int, status: str) -> list[dict[str, Any]]:
    records = load_candidate_records(root=_project_root())
    cards: list[dict[str, Any]] = []
    for record in records:
        if status and str(record.get("status") or "pending") != status:
            continue
        card = candidate_card(record)
        card["value"] = str(
            record.get("value")
            or record.get("result_excerpt")
            or record.get("evidence")
            or record.get("query")
            or ""
        )
        card["created_at"] = str(record.get("created_at") or record.get("timestamp") or "")
        artifact_path = Path(str(record.get("artifact") or ""))
        try:
            artifact_path.resolve().relative_to(_project_root().resolve())
            card["artifact_text"] = artifact_path.read_text(encoding="utf-8", errors="replace")[:50000]
        except (OSError, ValueError):
            card["artifact_text"] = ""
        cards.append(card)
    cards.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return cards[:limit]


def _job_snapshot(request: Request) -> dict[str, Any]:
    return dict(getattr(request.app.state, "curator_test_job", {"status": "idle"}))


async def _run_local_test_job(request: Request) -> None:
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pytest",
            "--testmon",
            "-n",
            "0",
            "-q",
            "--tb=short",
            cwd=str(_project_root()),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output_bytes, _ = await process.communicate()
        output = output_bytes.decode("utf-8", errors="replace")
        request.app.state.curator_test_job = {
            "status": "passed" if process.returncode == 0 else "failed",
            "exit_code": process.returncode,
            "output": output[-5000:],
        }
    except Exception as exc:
        request.app.state.curator_test_job = {
            "status": "failed",
            "exit_code": -1,
            "output": str(exc),
        }


@router.get("", dependencies=[Depends(_trusted_lan_or_local)])
async def curator_dashboard(request: Request, limit: int = 40, status: str = "") -> JSONResponse:
    cards = _candidate_cards(max(1, min(limit, 200)), status.strip())
    decisions = load_curation_decisions(root=_project_root(), limit=500)
    decision_counts = Counter(str(item.get("action") or "unknown") for item in decisions)
    status_counts = Counter(str(card.get("status") or "pending") for card in cards)
    return JSONResponse(
        {
            "ok": True,
            "candidates": cards,
            "candidate_count": len(cards),
            "status_counts": dict(status_counts),
            "decision_counts": dict(decision_counts),
            "quality": _latest_quality_comparison(),
            "test_job": _job_snapshot(request),
        }
    )


@router.post("/run", dependencies=[Depends(_trusted_lan_or_local)])
async def run_local_tests(request: Request) -> JSONResponse:
    task = getattr(request.app.state, "curator_test_task", None)
    if task is not None and not task.done():
        return JSONResponse({"ok": True, "test_job": _job_snapshot(request), "already_running": True})
    request.app.state.curator_test_job = {"status": "running", "exit_code": None, "output": ""}
    request.app.state.curator_test_task = asyncio.create_task(_run_local_test_job(request))
    return JSONResponse({"ok": True, "test_job": _job_snapshot(request)})


@router.post("/{candidate_id}/decision", dependencies=[Depends(_trusted_lan_or_local)])
async def decide_candidate(candidate_id: str, action: str) -> JSONResponse:
    if action not in {"promote", "reject", "defer"}:
        raise HTTPException(status_code=400, detail="action must be promote, reject, or defer")
    records = load_candidate_records(root=_project_root())
    candidate = next((item for item in records if str(item.get("candidate_id")) == candidate_id), None)
    if candidate is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    event = append_curation_decision(
        {
            "kind": "memory_candidate",
            "source": candidate.get("source", ""),
            "candidate_id": candidate_id,
            "session_id": candidate.get("session_id", ""),
            "action": action,
            "notes": "Decisión tomada desde el panel de diagnóstico.",
        },
        root=_project_root(),
    )
    return JSONResponse({"ok": True, "decision": event})
