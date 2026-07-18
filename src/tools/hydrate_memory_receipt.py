"""Tool: hydrate a compact memory receipt back into source context."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from src.memory.memory_db_path import resolve_memory_db_path
from src.utils.async_utils import run_in_thread

logger = logging.getLogger(__name__)

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "hydrate_memory_receipt",
        "description": (
            "Expand a compact memory receipt that appeared in the system context. "
            "Use its receipt ID to load the original memory, synthesis, or session "
            "exchange plus nearby conversational context. A query may be used to "
            "find matching receipt IDs from the current chat."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "receipt_id": {
                    "type": "string",
                    "description": "Receipt ID such as mr_0123456789abcdef.",
                    "default": "",
                },
                "query": {
                    "type": "string",
                    "description": "Search recent receipts when the exact ID is unknown.",
                    "default": "",
                },
                "context_window": {
                    "type": "integer",
                    "description": "Nearby session exchanges on each side (default 1, max 4).",
                    "default": 1,
                },
            },
        },
    },
}


def _matches_receipt(row: sqlite3.Row, receipt: dict[str, Any]) -> bool:
    if str(row["source"] or "") != str(receipt.get("source") or ""):
        return False
    if str(row["source_key"] or "") != str(receipt.get("source_key") or ""):
        return False
    if int(row["exchange_idx"] or 0) != int(receipt.get("item_idx", 0)):
        return False
    expected_hash = str(receipt.get("content_hash") or "")
    return not expected_hash or str(row["content_hash"] or "") == expected_hash


def _load_vector_source(receipt: dict[str, Any]) -> dict[str, Any]:
    path = Path(resolve_memory_db_path()).resolve()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = None
        vec_rowid = receipt.get("vec_rowid")
        if vec_rowid is not None:
            row = conn.execute(
                """
                SELECT rowid, source, source_key, exchange_idx, text, metadata,
                       created_at, content_hash
                FROM vec_meta
                WHERE rowid=?
                """,
                (int(vec_rowid),),
            ).fetchone()
            if row is not None and not _matches_receipt(row, receipt):
                row = None
        if row is None:
            content_hash = str(receipt.get("content_hash") or "")
            hash_clause = " AND content_hash=?" if content_hash else ""
            parameters: tuple[Any, ...] = (
                receipt.get("source", ""),
                receipt.get("source_key", ""),
                int(receipt.get("item_idx", 0)),
            )
            if content_hash:
                parameters += (content_hash,)
            row = conn.execute(
                f"""
                SELECT rowid, source, source_key, exchange_idx, text, metadata,
                       created_at, content_hash
                FROM vec_meta
                WHERE source=? AND source_key=? AND exchange_idx=?
                {hash_clause}
                ORDER BY rowid DESC
                LIMIT 1
                """,
                parameters,
            ).fetchone()
        return dict(row) if row else {}
    except sqlite3.Error:
        logger.info("Vector source unavailable while hydrating memory receipt", exc_info=True)
        return {}
    finally:
        conn.close()


def _message_parts(row: Any) -> tuple[str, str]:
    if hasattr(row, "keys"):
        return str(row["role"] or ""), str(row["content"] or "")
    return str(row[0] or ""), str(row[1] or "")


def _group_exchanges(rows: list[Any]) -> list[list[tuple[str, str]]]:
    exchanges: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    for row in rows:
        role, content = _message_parts(row)
        if role == "user" and current:
            exchanges.append(current)
            current = []
        current.append((role, content))
    if current:
        exchanges.append(current)
    return exchanges


def _format_exchange_context(rows: list[Any], item_idx: int, window: int) -> str:
    exchanges = _group_exchanges(rows)
    if not exchanges:
        return ""
    anchor = max(0, min(int(item_idx), len(exchanges) - 1))
    start = max(0, anchor - window)
    end = min(len(exchanges), anchor + window + 1)
    lines = []
    for index in range(start, end):
        marker = "anchor" if index == anchor else "nearby"
        lines.append(f"### Exchange {index} ({marker})")
        for role, content in exchanges[index]:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _format_indexed_exchange_context(rows: list[Any], item_idx: int) -> str:
    lines: list[str] = []
    current_idx: int | None = None
    for row in rows:
        if hasattr(row, "keys"):
            role = str(row["role"] or "")
            content = str(row["content"] or "")
            exchange_idx = int(row["exchange_idx"])
        else:
            role = str(row[0] or "")
            content = str(row[1] or "")
            exchange_idx = int(row[2])
        if exchange_idx != current_idx:
            marker = "anchor" if exchange_idx == item_idx else "nearby"
            lines.append(f"### Exchange {exchange_idx} ({marker})")
            current_idx = exchange_idx
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _format_candidates(rows: list[dict[str, Any]]) -> str:
    lines = ["Matching memory receipts:"]
    for row in rows:
        lines.append(
            f"- [{row['receipt_id']}] tag={row.get('tag', '')} "
            f"source={row.get('source', '')}:{row.get('source_key', '')}"
        )
        lines.append(f"  {row.get('excerpt', '')}")
    lines.append("Call hydrate_memory_receipt again with the chosen receipt_id.")
    return "\n".join(lines)


async def run(**kwargs) -> str:
    receipt_id = str(kwargs.get("receipt_id") or "").strip()
    query = str(kwargs.get("query") or "").strip()
    context_window = max(0, min(int(kwargs.get("context_window", 1)), 4))
    session_id = str(kwargs.get("_session_id") or "").strip()
    repos = kwargs.get("_repos")
    receipt_repo = getattr(repos, "memory_receipts", None) if repos is not None else None

    if not session_id:
        return "[ERROR] hydrate_memory_receipt requires the active session."
    if receipt_repo is None:
        return "[ERROR] Memory receipt repository is unavailable."
    if not receipt_id and not query:
        return "[ERROR] Provide receipt_id or query."

    if not receipt_id:
        matches = await receipt_repo.search(session_id, query, limit=5)
        if not matches:
            return f'No memory receipts matched "{query}".'
        if len(matches) > 1:
            return _format_candidates(matches)
        receipt_id = str(matches[0]["receipt_id"])

    receipt = await receipt_repo.get(session_id, receipt_id)
    if receipt is None:
        return "[ERROR] Receipt not found in the active session."

    vector_source = await run_in_thread(_load_vector_source, receipt)
    source = str(receipt.get("source") or "")
    source_key = str(receipt.get("source_key") or "")
    full_text = str(vector_source.get("text") or receipt.get("excerpt") or "")
    session_context = ""

    if source == "memory" and repos is not None:
        canonical = await repos.memory.memory_index.get(source_key)
        if canonical:
            full_text = str(canonical)
    elif source == "session" and repos is not None:
        item_idx = int(receipt.get("item_idx", 0))
        get_window = getattr(repos.messages, "get_session_exchange_window", None)
        if get_window is not None:
            messages = await get_window(source_key, item_idx, context_window)
            session_context = _format_indexed_exchange_context(messages, item_idx)
        else:
            messages = await repos.messages.get_session_messages(source_key, limit=500)
            session_context = _format_exchange_context(messages, item_idx, context_window)

    await receipt_repo.touch_hydrated(session_id, receipt_id)
    metadata = vector_source.get("metadata")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            pass

    lines = [
        f"# Hydrated memory receipt [{receipt_id}]",
        f"- tag: {receipt.get('tag', '')}",
        f"- source: {source}:{source_key}",
        f"- item_idx: {receipt.get('item_idx', 0)}",
        f"- originally activated by: {receipt.get('trigger_query', '')}",
        "",
        "## Full remembered source",
        full_text,
    ]
    if metadata:
        lines.extend(["", "## Source metadata", json.dumps(metadata, ensure_ascii=False)])
    if session_context:
        lines.extend(["", "## Surrounding session context", session_context])
    return "\n".join(lines)


__all__ = ["DEFINITION", "run"]
