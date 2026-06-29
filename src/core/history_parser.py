import json
import logging
from datetime import datetime
from typing import Any

from src.core.history_contract import HistoryMessage

logger = logging.getLogger(__name__)


def _get_row_value(row: Any, key: str, default: Any = None) -> Any:
    if hasattr(row, "get"):
        try:
            return row.get(key, default)
        except TypeError:
            pass
    try:
        return row[key]
    except Exception:
        return getattr(row, key, default)


def _parse_rows(rows: list[Any]) -> list[HistoryMessage]:
    raw_msgs = []
    for row in rows:
        role = _get_row_value(row, "role")
        content = _get_row_value(row, "content")
        created_at = _get_row_value(row, "created_at")
        tool_calls = _get_row_value(row, "tool_calls")
        tool_call_id = _get_row_value(row, "tool_call_id")
        reasoning = _get_row_value(row, "reasoning")

        if role == "system":
            continue

        try:
            dt = datetime.fromisoformat(created_at)
            ts_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            logger.exception("Failed to parse datetime: %s", created_at)
            ts_str = created_at

        parsed_tool_calls = None
        if tool_calls:
            try:
                parsed_tool_calls = json.loads(tool_calls) if isinstance(tool_calls, str) else tool_calls
            except Exception:
                logger.exception("Failed to parse tool_calls payload")
                parsed_tool_calls = None

        parsed_reasoning = reasoning or ""
        parsed_content: str | None
        if role == "assistant" and parsed_tool_calls and (content is None or content == ""):
            parsed_content = None
        else:
            parsed_content = f"[{ts_str}] {content}" if content else f"[{ts_str}]"

        raw_msgs.append(
            HistoryMessage(
                role=role,
                content=parsed_content,
                created_at=created_at,
                reasoning=parsed_reasoning,
                phases=_get_row_value(row, "phases") or "[]",
                tool_calls=parsed_tool_calls,
                tool_call_id=tool_call_id,
                id=_get_row_value(row, "id"),
            )
        )
    return raw_msgs


def _copy_message(msg: HistoryMessage, **updates: Any) -> HistoryMessage:
    if hasattr(msg, "model_copy"):
        return msg.model_copy(update=updates)
    return msg.copy(update=updates)


def _sanitize_messages(raw_msgs: list[HistoryMessage]) -> list[HistoryMessage]:
    sanitized = []
    idx = 0

    while idx < len(raw_msgs):
        msg = raw_msgs[idx]
        role = msg.role

        if role == "assistant" and msg.tool_calls:
            tool_call_ids = {tc.get("id") for tc in msg.tool_calls if tc.get("id")}
            consecutive_tool_msgs: list[HistoryMessage] = []
            responded_tool_ids: set[str] = set()
            scan_idx = idx + 1

            while scan_idx < len(raw_msgs) and raw_msgs[scan_idx].role == "tool":
                tool_msg = raw_msgs[scan_idx]
                if tool_msg.tool_call_id in tool_call_ids and tool_msg.tool_call_id not in responded_tool_ids:
                    consecutive_tool_msgs.append(tool_msg)
                    responded_tool_ids.add(tool_msg.tool_call_id)
                scan_idx += 1

            filtered_tcs = [tc for tc in msg.tool_calls if tc.get("id") in responded_tool_ids]
            if filtered_tcs:
                sanitized.append(_copy_message(msg, tool_calls=filtered_tcs))
                sanitized.extend(consecutive_tool_msgs)
            elif msg.content:
                sanitized.append(_copy_message(msg, tool_calls=None))

            idx = scan_idx
            continue

        if role == "tool":
            idx += 1
            continue

        sanitized.append(msg)
        idx += 1

    return sanitized
