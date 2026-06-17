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


def _sanitize_messages(raw_msgs: list[HistoryMessage]) -> list[HistoryMessage]:
    tool_responses = set()
    for msg in raw_msgs:
        if msg.role == "tool" and msg.tool_call_id:
            tool_responses.add(msg.tool_call_id)

    sanitized = []
    valid_tool_call_ids = set()
    pending_tool_call_ids: set[str] = set()

    for msg in raw_msgs:
        role = msg.role
        if role == "assistant":
            tool_calls = msg.tool_calls
            if tool_calls:
                filtered_tcs = [tc for tc in tool_calls if tc.get("id") in tool_responses]
                if filtered_tcs:
                    msg.tool_calls = filtered_tcs
                    for tc in filtered_tcs:
                        valid_tool_call_ids.add(tc.get("id"))
                        pending_tool_call_ids.add(tc.get("id"))
                else:
                    msg.tool_calls = None
                    if not msg.content:
                        continue
            else:
                if pending_tool_call_ids:
                    continue
            sanitized.append(msg)
        elif role == "tool":
            tcid = msg.tool_call_id
            if tcid in valid_tool_call_ids:
                sanitized.append(msg)
                pending_tool_call_ids.discard(tcid)
        else:
            if pending_tool_call_ids:
                pending_tool_call_ids.clear()
            sanitized.append(msg)
    return sanitized
