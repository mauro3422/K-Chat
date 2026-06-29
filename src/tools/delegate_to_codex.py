"""Delegate a concrete work item to Codex on the primary LAN node."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx


DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "delegate_to_codex",
        "description": (
            "Create a work task for Codex on the primary PC. Use this when Mauro is on a secondary node "
            "and wants Codex to make a code/docs/config change, investigate a bug, or run an operational task."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short task title for Codex.",
                },
                "prompt": {
                    "type": "string",
                    "description": "Concrete instructions, context, expected outcome, and anything Codex must report back.",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "normal", "high", "urgent"],
                    "default": "normal",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional Kairos session id that originated the task.",
                    "default": "",
                },
            },
            "required": ["title", "prompt"],
        },
    },
}


def _bridge_url() -> str:
    raw = os.getenv("KAIROS_CODEX_BRIDGE_URL") or os.getenv("KAIROS_PRIMARY_URL") or "http://127.0.0.1:8000"
    return raw.rstrip("/")


async def run(
    title: str,
    prompt: str,
    priority: str = "normal",
    session_id: str = "",
    _session_id: str | None = None,
) -> str:
    if not title.strip():
        return "[ERROR] title is required."
    if not prompt.strip():
        return "[ERROR] prompt is required."

    payload = {
        "title": title,
        "prompt": prompt,
        "priority": priority,
        "session_id": session_id or _session_id or "",
        "from_node": os.getenv("KAIROS_NODE_ID", ""),
    }
    url = f"{_bridge_url()}/api/codex/tasks"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        return f"[ERROR] Could not delegate task to Codex via {url}: {exc}"

    try:
        data = response.json()
    except json.JSONDecodeError:
        return f"[ERROR] Codex bridge returned non-JSON response from {url}."
    task = data.get("task") if isinstance(data, dict) else None
    if not isinstance(task, dict):
        return f"[ERROR] Codex bridge returned an invalid task response from {url}."
    return f"[OK] Delegated to Codex: {task.get('id')} status={task.get('status')} title={task.get('title')}"
