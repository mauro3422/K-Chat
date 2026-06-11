import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def _parse_rows(rows: list[Any]) -> list[dict[str, Any]]:
    raw_msgs = []
    for row in rows:
        role = row[0]
        content = row[1]
        created_at = row[3]
        tool_calls = row[6] if len(row) > 6 else None
        tool_call_id = row[7] if len(row) > 7 else None
        reasoning = row[4] if len(row) > 4 else None

        if role == "system":
            continue

        try:
            dt = datetime.fromisoformat(created_at)
            ts_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            logger.exception("Failed to parse datetime: %s", created_at)
            ts_str = created_at

        msg = {"role": role}
        if role == "assistant" and tool_calls and (content is None or content == ""):
            msg["content"] = None
        else:
            msg["content"] = f"[{ts_str}] {content}" if content else f"[{ts_str}]"

        if role == "assistant":
            if tool_calls:
                msg["tool_calls"] = json.loads(tool_calls)
            if reasoning:
                msg["reasoning_content"] = reasoning
        elif role == "tool":
            if tool_call_id:
                msg["tool_call_id"] = tool_call_id

        raw_msgs.append(msg)
    return raw_msgs


def _sanitize_messages(raw_msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tool_responses = set()
    for msg in raw_msgs:
        if msg.get("role") == "tool" and msg.get("tool_call_id"):
            tool_responses.add(msg["tool_call_id"])

    sanitized = []
    valid_tool_call_ids = set()
    pending_tool_call_ids: set[str] = set()

    for msg in raw_msgs:
        role = msg.get("role")
        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                filtered_tcs = [tc for tc in tool_calls if tc.get("id") in tool_responses]
                if filtered_tcs:
                    msg["tool_calls"] = filtered_tcs
                    for tc in filtered_tcs:
                        valid_tool_call_ids.add(tc.get("id"))
                        pending_tool_call_ids.add(tc.get("id"))
                else:
                    msg.pop("tool_calls", None)
                    if not msg.get("content"):
                        continue
            else:
                if pending_tool_call_ids:
                    continue
            sanitized.append(msg)
        elif role == "tool":
            tcid = msg.get("tool_call_id")
            if tcid in valid_tool_call_ids:
                sanitized.append(msg)
                pending_tool_call_ids.discard(tcid)
        else:
            if pending_tool_call_ids:
                pending_tool_call_ids.clear()
            sanitized.append(msg)
    return sanitized
