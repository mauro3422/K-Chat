import json
from typing import Any

from src.api.debug import save_debug_info
from src.api.messages import save_message as db_save_message


def _dedup_phases(phases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not phases:
        return phases
    result = [phases[0]]
    for phase in phases[1:]:
        prev = result[-1]
        if phase.get("content") != prev.get("content") or phase.get("reasoning") != prev.get("reasoning"):
            result.append(phase)
    return result


def save_assistant_message(
    session_id: str,
    full_content: str,
    full_reasoning: str,
    phases_output: list[dict[str, Any]],
    debug_info: dict[str, Any],
    model: str,
) -> None:
    """Persists the assistant message and debug info to the database."""
    phases_output[:] = _dedup_phases(phases_output)
    phases_json = json.dumps(phases_output, ensure_ascii=False)
    pt = debug_info.get("prompt_tokens", 0)
    ct = debug_info.get("completion_tokens", 0)
    tt = debug_info.get("total_tokens", 0)
    db_save_message(
        session_id, "assistant", full_content, model,
        reasoning=full_reasoning, phases=phases_json,
        prompt_tokens=pt, completion_tokens=ct, total_tokens=tt,
    )
    if not debug_info.get("phases"):
        debug_info["phases"] = phases_json
    save_debug_info(session_id, debug_info)
