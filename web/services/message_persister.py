import json
import time
from typing import Any

from src.api import DebugInfo, MessageRecord, get_repos
from web.services.message_persister_contract import MessagePersisterDeps


def _dedup_phases(phases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not phases:
        return phases
    result = [phases[0]]
    for phase in phases[1:]:
        prev = result[-1]
        if phase.get("content") != prev.get("content") or phase.get("reasoning") != prev.get("reasoning"):
            result.append(phase)
    return result


def _resolve_persister_deps(deps: MessagePersisterDeps | None = None) -> MessagePersisterDeps:
    return deps or MessagePersisterDeps()


async def save_assistant_message(
    session_id: str,
    full_content: str,
    full_reasoning: str,
    phases_output: list[dict[str, Any]],
    debug_info: DebugInfo,
    model: str,
    repos: 'Repositories | None' = None,
    deps: MessagePersisterDeps | None = None,
) -> None:
    """Persists the assistant message and debug info to the database."""
    _deps = _resolve_persister_deps(deps)
    record_cls = _deps.message_record_cls or MessageRecord

    if repos is None:
        repos = get_repos()

    phases_output[:] = _dedup_phases(phases_output)
    phases_json = json.dumps(phases_output, ensure_ascii=False)
    pt = debug_info.prompt_tokens
    ct = debug_info.completion_tokens
    tt = debug_info.total_tokens
    record = record_cls(
        session_id=session_id,
        role="assistant",
        content=full_content,
        model=model,
        reasoning=full_reasoning,
        phases=phases_json,
        prompt_tokens=pt,
        completion_tokens=ct,
        total_tokens=tt,
    )
    if _deps.save_message_fn is not None:
        await _deps.save_message_fn(record)
    else:
        await repos.messages.save_record(record)
    if not debug_info.phases or debug_info.phases == "[]":
        debug_info.phases = phases_json
    if _deps.save_debug_fn is not None:
        _deps.save_debug_fn(session_id, debug_info.to_dict())
    else:
        await repos.debug.save_info(session_id, debug_info.to_dict())

    try:
        from src.api import log_turn
        log_turn(
            session_id=session_id,
            user_msg="",
            assistant_msg=full_content,
            tools_used=[],
            model=model,
            duration_ms=0,
            token_count=tt,
            error="",
        )
    except Exception:
        pass
