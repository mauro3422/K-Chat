"""Compact handles for memory blocks that were previously injected."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable


def _compact(text: str, limit: int) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(1, limit - 1)].rstrip() + "…"


def build_memory_receipt(session_id: str, result: Any, trigger_query: str) -> dict[str, Any]:
    source = str(getattr(result, "source", "") or "unknown")
    source_key = str(getattr(result, "source_key", "") or "")
    item_idx = int(getattr(result, "item_idx", 0) or 0)
    identity = f"{session_id}\0{source}\0{source_key}\0{item_idx}"
    receipt_id = "mr_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    label = source_key or f"row:{int(getattr(result, 'rowid', 0) or 0)}"
    return {
        "receipt_id": receipt_id,
        "source": source,
        "source_key": source_key,
        "item_idx": item_idx,
        "vec_rowid": int(getattr(result, "rowid", 0) or 0) or None,
        "content_hash": str(getattr(result, "content_hash", "") or ""),
        "tag": _compact(f"{source}:{label}", 96),
        "excerpt": _compact(str(getattr(result, "text", "") or ""), 240),
        "trigger_query": _compact(trigger_query, 200),
    }


def format_receipt_ledger(
    receipts: Iterable[dict[str, Any]],
    *,
    total_count: int | None = None,
) -> str:
    materialized = list(receipts)
    if not materialized and not total_count:
        return ""

    total = int(total_count if total_count is not None else len(materialized))
    lines = [
        "## Memory receipt ledger",
        (
            "These compact handles refer to memories injected earlier in this chat. "
            "Their full text is intentionally not repeated. If one becomes relevant "
            "and details are needed, call `hydrate_memory_receipt` with its ID. "
            "Do not invent details that are not present in the receipt."
        ),
        f"Available receipts in this session: {total}. Showing {len(materialized)} recent handles.",
        "",
    ]
    for receipt in materialized:
        lines.append(
            f"- [{receipt.get('receipt_id', '')}] "
            f"tag={receipt.get('tag', '')} "
            f"source={receipt.get('source', '')}:{receipt.get('source_key', '')}"
        )
        lines.append(f"  context: {_compact(str(receipt.get('excerpt', '')), 180)}")
        trigger = _compact(str(receipt.get("trigger_query", "")), 100)
        if trigger:
            lines.append(f"  activated_by: {trigger}")
    return "\n".join(lines)


__all__ = ["build_memory_receipt", "format_receipt_ledger"]
