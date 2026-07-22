import asyncio
import importlib
import json
import logging
import time
from collections.abc import AsyncGenerator, Callable
from typing import Any

from fastapi import BackgroundTasks

from src.api.background import auto_rename_session
from src.api.orchestrator import OrchestratorDeps, chat_stream
from src.api.repos import DebugInfo
from web.services.chat_stream_contract import StreamGeneratorDeps
from web.services.loop_detector import LoopDetector
from web.services.message_persister import save_assistant_message
from web.services.protocols import (
    MessagePersisterProtocol,
    SessionArtifactCoordinatorProtocol,
    StreamGeneratorProtocol,
)
from web.services.stream_contract import serialize_stream_event
from web.services.stream_error_classifier import classify_error
from web.services.stream_retry_handler import StreamRetryHandler
from web.services.stream_state import StreamState

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 20
MAX_STREAM_SILENCE = 15 * 60


async def _with_stream_heartbeats(
    source: AsyncGenerator[tuple[str, Any], None],
) -> AsyncGenerator[tuple[str, Any], None]:
    """Keep HTTP streams alive while the model or a tool is still working."""
    iterator = source.__aiter__()
    pending: asyncio.Task[Any] | None = None
    silent_for = 0.0
    try:
        pending = asyncio.create_task(iterator.__anext__())
        while True:
            done, _ = await asyncio.wait(
                {pending},
                timeout=HEARTBEAT_INTERVAL,
            )
            if not done:
                silent_for += HEARTBEAT_INTERVAL
                if silent_for >= MAX_STREAM_SILENCE:
                    raise TimeoutError(
                        "Stream produced no model or tool events for "
                        f"{int(silent_for)} seconds"
                    )
                yield "heartbeat", ""
                continue

            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            silent_for = 0.0
            yield event
            pending = asyncio.create_task(iterator.__anext__())
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        close = getattr(iterator, "aclose", None)
        if callable(close):
            await close()


def _history_json(history: list[Any]) -> str:
    items: list[dict[str, Any]] = []
    for message in history:
        if isinstance(message, dict):
            items.append(dict(message))
        elif callable(getattr(message, "as_llm_message", None)):
            items.append(message.as_llm_message())
        else:
            items.append({
                "role": getattr(message, "role", ""),
                "content": getattr(message, "content", None),
            })
    return json.dumps(items, ensure_ascii=False)


def build_stream_generator(
    session_id: str,
    message: str,
    history: list[dict[str, Any]],
    model: str,
    background_tasks: BackgroundTasks,
    chat_stream_fn: Callable[..., AsyncGenerator[Any, None]] | None = None,
    loop_detector: LoopDetector | None = None,
    retry_handler: StreamRetryHandler | None = None,
    save_fn: MessagePersisterProtocol | None = None,
    rename_fn: Callable | None = None,
    deps: StreamGeneratorDeps | None = None,
    orchestrator_deps: OrchestratorDeps | None = None,
) -> StreamGeneratorProtocol:
    """Build the NDJSON generator and durable recovery checkpoints."""
    _deps = deps or StreamGeneratorDeps(
        chat_stream_fn=chat_stream_fn,
        loop_detector=loop_detector,
        retry_handler=retry_handler,
        save_fn=save_fn,
        rename_fn=rename_fn,
    )
    _chat_stream = _deps.chat_stream_fn or chat_stream

    async def generate() -> AsyncGenerator[str, None]:
        if orchestrator_deps is None:
            raise ValueError(
                "orchestrator_deps is required. Pass OrchestratorDeps from "
                "the composition root (request.app.state)."
            )

        debug_info = DebugInfo()
        phases_output: list[dict[str, Any]] = [
            dict(phase) for phase in _deps.initial_phases
        ]
        clock = _deps.clock or time.monotonic
        state = StreamState(
            save_interval=10,
            last_persisted_at=clock(),
        )
        detector = _deps.loop_detector or LoopDetector()
        save_message = _deps.save_fn or save_assistant_message
        rename_session = _deps.rename_fn or auto_rename_session
        orch_deps = orchestrator_deps
        orch_deps.debug = debug_info
        orch_deps.phases_output = phases_output
        checkpoint_repo = getattr(orch_deps.repos, "stream_checkpoints", None)
        completed = False
        last_error_type = _deps.retry_error_type
        last_error_message = _deps.retry_error_message

        logger.info("Starting chat for session %s with model %s", session_id, model)

        async def save_final(description: str) -> bool:
            retry_marker = next(
                (phase["retry"] for phase in reversed(phases_output)
                 if isinstance(phase.get("retry"), dict)),
                None,
            )
            previous_retry_status = None
            if retry_marker is not None:
                previous_retry_status = retry_marker.get("status")
                retry_marker["status"] = "completed"
            for attempt in range(3):
                try:
                    await save_message(
                        session_id,
                        state.full_content,
                        state.full_reasoning,
                        phases_output,
                        debug_info,
                        model,
                    )
                    state.mark_persisted(clock())
                    logger.info(
                        "Final save OK (%s): %d chars",
                        description,
                        len(state.full_content),
                    )
                    return True
                except Exception as exc:
                    logger.warning(
                        "Final save failed (%s) (attempt %d/3): %s",
                        description,
                        attempt + 1,
                        exc,
                    )
                    if attempt < 2:
                        await asyncio.sleep(1.0 * (2 ** attempt))
            if retry_marker is not None:
                retry_marker["status"] = previous_retry_status or "active"
            return False

        async def save_checkpoint(
            kind: str,
            *,
            status: str = "open",
            error_type: str = "",
            error_message: str = "",
        ) -> None:
            if checkpoint_repo is None:
                return
            try:
                await checkpoint_repo.save(
                    session_id,
                    original_message=_deps.original_message or message,
                    model=model,
                    history_json=_history_json(history),
                    phases_json=json.dumps(phases_output, ensure_ascii=False),
                    partial_content=state.full_content,
                    partial_reasoning=state.full_reasoning,
                    status=status,
                    checkpoint_kind=kind,
                    error_type=error_type,
                    error_message=error_message,
                    retry_count=_deps.retry_count,
                )
                state.last_persisted_at = clock()
            except Exception:
                logger.exception(
                    "Checkpoint save failed for %s (%s)",
                    session_id,
                    kind,
                )

        async def clear_checkpoint() -> None:
            if checkpoint_repo is None:
                return
            try:
                await checkpoint_repo.clear(session_id)
            except Exception:
                logger.exception("Checkpoint clear failed for %s", session_id)

        async def recovery_events(
            error_type: str,
            error_message: str,
            *,
            allow_empty: bool = False,
        ) -> AsyncGenerator[tuple[str, Any], None]:
            if (
                _deps.retry_handler is None
                or not _deps.retry_handler.can_retry
                or (not allow_empty and not state.has_progress())
            ):
                return
            retry_count = getattr(_deps.retry_handler, "retry_count", 0)
            max_retries = getattr(_deps.retry_handler, "max_retries", 2)
            if not isinstance(retry_count, int):
                retry_count = 0
            if not isinstance(max_retries, int):
                max_retries = 2
            retry_data = {
                "attempt": retry_count + 1,
                "max_retries": max_retries,
                "error_type": error_type,
                "error_message": error_message,
                "checkpoint_kind": "last_confirmed",
                "status": "active",
            }
            phases_output.append({"retry": dict(retry_data)})
            yield "retry", retry_data
            recovery_source = _deps.retry_handler.attempt_recovery(
                history,
                state.full_content,
                state.full_reasoning,
                model,
                session_id,
                stream_fn=_chat_stream,
                orchestrator_deps=orch_deps,
                error_type=error_type,
                error_message=error_message,
            )
            async for recovery_type, recovery_token in _with_stream_heartbeats(
                recovery_source,
            ):
                yield recovery_type, recovery_token

        async def consume_event(
            event_type: str,
            token: Any,
        ) -> AsyncGenerator[str, None]:
            if event_type == "checkpoint":
                kind = token.get("kind", "phase") if isinstance(token, dict) else "phase"
                await save_checkpoint(kind)
                if kind == "tool_phase":
                    state.close_phase()
                return
            if event_type == "heartbeat":
                yield serialize_stream_event("heartbeat", "")
                return
            if event_type != "tool_call":
                state.append(event_type, token)
            yield serialize_stream_event(event_type, token)

        try:
            recovered_from_loop = False
            source = _chat_stream(
                message,
                history,
                model,
                deps=orch_deps,
            )
            async for event_type, token in _with_stream_heartbeats(source):
                if event_type == "content":
                    loop_error = detector.check(token)
                    if loop_error:
                        last_error_type = "loop_detected"
                        last_error_message = loop_error
                        await save_checkpoint(
                            "loop_detected",
                            status="interrupted",
                            error_type=last_error_type,
                            error_message=last_error_message,
                        )
                        try:
                            async for recovery_type, recovery_token in recovery_events(
                                last_error_type,
                                last_error_message,
                                allow_empty=True,
                            ):
                                async for line in consume_event(recovery_type, recovery_token):
                                    yield line
                                if recovery_type != "retry":
                                    recovered_from_loop = True
                        except Exception:
                            logger.exception(
                                "Loop recovery failed for %s",
                                session_id,
                            )
                        if not recovered_from_loop:
                            yield serialize_stream_event(
                                "error",
                                {
                                    "type": last_error_type,
                                    "message": last_error_message,
                                },
                            )
                        break

                async for line in consume_event(event_type, token):
                    yield line

                if state.should_persist(clock()):
                    await save_checkpoint("periodic")

            if not state.has_output():
                last_error_type = "empty_response"
                last_error_message = "The model did not generate any content"
                await save_checkpoint(
                    "empty_response",
                    status="interrupted",
                    error_type=last_error_type,
                    error_message=last_error_message,
                )
                yield serialize_stream_event(
                    "error",
                    {"type": last_error_type, "message": last_error_message},
                )
                return

            saved = not state.dirty or await save_final("final")
            if saved:
                await clear_checkpoint()
                completed = True
                background_tasks.add_task(
                    rename_session,
                    session_id,
                    _deps.original_message or message,
                    model,
                )

        except GeneratorExit:
            logger.info("Client disconnected for %s", session_id)
            return
        except Exception as exc:
            last_error_type, last_error_message = classify_error(exc)
            logger.error(
                "Stream error for %s: [%s] %s - %s: %s",
                session_id,
                last_error_type,
                last_error_message,
                type(exc).__name__,
                exc,
            )
            await save_checkpoint(
                "stream_error",
                status="interrupted",
                error_type=last_error_type,
                error_message=last_error_message,
            )

            recovered = False
            try:
                async for recovery_type, recovery_token in recovery_events(
                    last_error_type,
                    last_error_message,
                ):
                    async for line in consume_event(recovery_type, recovery_token):
                        yield line
                    if recovery_type != "retry":
                        recovered = True
            except Exception:
                logger.exception("Recovery also failed for %s", session_id)

            if recovered and state.has_output():
                saved = not state.dirty or await save_final("recovered")
                if saved:
                    await clear_checkpoint()
                    completed = True
                return

            yield serialize_stream_event(
                "error",
                {"type": last_error_type, "message": last_error_message},
            )
            return
        finally:
            background_tasks.add_task(
                _vectorize_session,
                session_id,
                orch_deps,
                _deps.session_artifact_coordinator,
            )
            if not completed:
                await save_checkpoint(
                    "interruption",
                    status="interrupted",
                    error_type=last_error_type,
                    error_message=last_error_message,
                )

    return generate


async def _run_vectorization_pipeline(session_id: str, repos: Any) -> None:
    """Run the vectorization pipeline after coordination and existence checks."""
    vectorize = importlib.import_module(
        "src.memory.vectorize_sessions"
    ).vectorize_session
    heuristic_mod = importlib.import_module("src.memory.clustering.heuristic")
    relations_mod = importlib.import_module("src.memory.clustering.relations")
    linker_mod = importlib.import_module("src.memory.entity.linker")
    resolve_memory_db_path = importlib.import_module(
        "src.memory.memory_db_path"
    ).resolve_memory_db_path
    clusterer = heuristic_mod.HeuristicClusterer()
    linker = linker_mod.EntityLinker()
    db_path = resolve_memory_db_path()

    count, noise, mappings, _ = await vectorize(
        session_id,
        clusterer=clusterer,
        repos=repos,
        linker=linker,
    )
    if count <= 0:
        return

    await heuristic_mod.flush_clusters_to_db(
        clusterer,
        db_path,
        mappings=mappings,
    )
    cluster_dicts = [cluster.as_dict for cluster in clusterer.clusters.values()]
    relations = relations_mod.detect_relations(cluster_dicts)
    if relations:
        await relations_mod.flush_relations_to_db(relations, db_path)

    await linker_mod.flush_entities_to_db(linker, db_path)
    await linker_mod.flush_relations_to_db(linker, db_path)
    await linker_mod.flush_entity_mentions_to_db(linker, db_path)

    logger.info(
        "Vectorized session %s: %d exchanges (%d noise, %d clusters, %d entities)",
        session_id,
        count,
        noise,
        len(clusterer.clusters),
        len(linker.get_entities()),
    )


async def _vectorize_session(
    session_id: str,
    orchestrator_deps: OrchestratorDeps | None = None,
    coordinator: SessionArtifactCoordinatorProtocol | None = None,
) -> None:
    """Vectorize a session without racing destructive artifact cleanup."""
    if coordinator is None:
        logger.error(
            "Skipping vectorization for %s: session artifact coordinator is required",
            session_id,
        )
        return

    try:
        if not orchestrator_deps or not orchestrator_deps.repos:
            raise ValueError(
                "_vectorize_session requires orchestrator_deps.repos. "
                "Inject via the composition root."
            )
        repos = orchestrator_deps.repos
        async with coordinator.coordinate(session_id):
            if not await repos.sessions.exists(session_id):
                logger.info(
                    "Skipping vectorization for deleted session %s",
                    session_id,
                )
                return
            await _run_vectorization_pipeline(session_id, repos)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Failed to vectorize session %s (non-fatal)", session_id)
