import json
from typing import Any

from src.api.debug import save_debug_info
from src.api.messages import save_message_record as db_save_message
from src.core.debug_info import DebugInfo
from src.memory.repos import MessageRecord
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


def save_assistant_message(
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
    save_message_fn = _deps.save_message_fn or db_save_message
    save_debug_fn = _deps.save_debug_fn or save_debug_info
    record_cls = _deps.message_record_cls or MessageRecord

    if repos is None:
        from src.memory.repos import get_repos as _get_repos
        repos = _get_repos()

    phases_output[:] = _dedup_phases(phases_output)
    phases_json = json.dumps(phases_output, ensure_ascii=False)
    pt = debug_info.prompt_tokens
    ct = debug_info.completion_tokens
    tt = debug_info.total_tokens
    if _deps.save_message_fn is not None:
        try:
            save_message_fn(
                record_cls(
                    session_id=session_id,
                    role="assistant",
                    content=full_content,
                    model=model,
                    reasoning=full_reasoning,
                    phases=phases_json,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    total_tokens=tt,
                ),
                repos=repos,
            )
        except TypeError:
            save_message_fn(
                record_cls(
                    session_id=session_id,
                    role="assistant",
                    content=full_content,
                    model=model,
                    reasoning=full_reasoning,
                    phases=phases_json,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    total_tokens=tt,
                ),
            )
    else:
        save_message_fn(
            record_cls(
                session_id=session_id,
                role="assistant",
                content=full_content,
                model=model,
                reasoning=full_reasoning,
                phases=phases_json,
                prompt_tokens=pt,
                completion_tokens=ct,
                total_tokens=tt,
            ),
            repos=repos,
        )
    if not debug_info.phases or debug_info.phases == "[]":
        debug_info.phases = phases_json
    save_debug_fn(session_id, debug_info.to_dict())

