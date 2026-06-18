import logging
import asyncio
import time
import importlib
from collections.abc import Callable, AsyncGenerator
from typing import Any

from fastapi import BackgroundTasks

from src.api import (
    chat_stream,
    OrchestratorDeps,
    auto_rename_session,
)
from src.api.repos import DebugInfo
from web.services.loop_detector import LoopDetector
from web.services.message_persister import save_assistant_message
from web.services.stream_error_classifier import classify_error
from web.services.stream_retry_handler import StreamRetryHandler
from web.services.stream_contract import serialize_stream_event
from web.services.chat_stream_contract import StreamGeneratorDeps
from web.services.protocols import MessagePersisterProtocol, StreamGeneratorProtocol
from web.services.stream_state import StreamState

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 20

# Per-session locks to prevent data races between concurrent vectorization
# and delete operations for the same session_id.
_vectorize_locks: dict[str, asyncio.Lock] = {}


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
    """Builds the NDJSON generator for the chat stream."""
    _deps = deps or StreamGeneratorDeps(
        chat_stream_fn=chat_stream_fn,
        loop_detector=loop_detector,
        retry_handler=retry_handler,
        save_fn=save_fn,
        rename_fn=rename_fn,
    )
    _chat_stream = _deps.chat_stream_fn or chat_stream

    async def generate() -> AsyncGenerator[str, None]:
        debug_info = DebugInfo()
        phases_output = []
        state = StreamState()

        logger.info("Starting chat for session %s with model %s", session_id, model)

        async def _save_with_retry(desc: str = "") -> bool:
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    await _save(session_id, state.full_content, state.full_reasoning, phases_output, debug_info, model)
                    logger.info("Save OK%s: %d chars", f" ({desc})" if desc else "", len(state.full_content))
                    return True
                except Exception as e:
                    logger.warning("Save failed%s (attempt %d/%d): %s", f" ({desc})" if desc else "", attempt + 1, max_attempts, e)
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(1.0 * (2 ** attempt))
            return False

        detector = _deps.loop_detector or LoopDetector()
        _save = _deps.save_fn or save_assistant_message
        _rename = _deps.rename_fn or auto_rename_session
        last_save_time = time.monotonic()
        save_interval = 30

        # Prepare orchestrator dependencies (injected from composition root)
        if orchestrator_deps is None:
            raise ValueError(
                "orchestrator_deps is required. Pass OrchestratorDeps from "
                "the composition root (request.app.state)."
            )
        _orch_deps = orchestrator_deps
        _orch_deps.debug = debug_info
        _orch_deps.phases_output = phases_output

        try:
            async for tipo, token in _chat_stream(message, history, model, deps=_orch_deps):
                now = time.monotonic()

                if tipo == "heartbeat":
                    yield serialize_stream_event("heartbeat", "")
                    continue

                # 🛑 Cuando se ejecutan tools, el contenido del turno actual
                # YA fue guardado por _save_assistant_tool_calls en tool_loop.
                # Reseteamos buffers para evitar acumulación entre turns
                # (bug: mensajes concatenados en la DB).
                if tipo == "tool_call":
                    state.reset_on_tool_call()
                if tipo == "content":
                    loop_error = detector.check(token)
                    if loop_error:
                        logger.warning("Loop detected for %s: %s", session_id, loop_error)

                        recovered = False
                        if _deps.retry_handler is not None and _deps.retry_handler.can_retry:
                            logger.info(
                                "Transparent recovery (attempt %d/%d) for %s",
                                _deps.retry_handler.retry_count + 1,
                                _deps.retry_handler.max_retries,
                                session_id,
                            )
                            try:
                                async for rtipo, rtoken in _deps.retry_handler.attempt_recovery(
                                    history, state.full_content, state.full_reasoning,
                                    model, session_id,
                                ):
                                    state.append(rtipo, rtoken)
                                    yield serialize_stream_event(rtipo, rtoken)
                                    recovered = True
                            except Exception as e:
                                logger.error("Recovery failed for %s: %s", session_id, e)

                        if not recovered:
                            yield serialize_stream_event("error", {"type": "loop_detected", "message": loop_error})

                        break  # Exit main stream regardless of recovery outcome

                state.append(tipo, token)

                yield serialize_stream_event(tipo, token)

                if now - last_save_time > save_interval and state.has_output():
                    if await _save_with_retry("periodic"):
                        state.mark_persisted(now)
                        last_save_time = now

            if not state.has_output():
                logger.warning("Empty response for session %s with model %s", session_id, model)
                yield serialize_stream_event("error", {"type": "empty_response", "message": "The model did not generate any content"})
                return

            logger.info("Chat completed for session %s: %d chars content, %d chars reasoning", session_id, len(state.full_content), len(state.full_reasoning))

            if await _save_with_retry("final"):
                state.mark_persisted(now)
            background_tasks.add_task(_rename, session_id, message, model)

        except GeneratorExit:
            logger.info("Client disconnected for %s", session_id)
            return
        except Exception as e:
            error_type, error_msg = classify_error(e)
            logger.error("Stream error for %s: [%s] %s — %s: %s", session_id, error_type, error_msg, type(e).__name__, e)
            if _deps.retry_handler is not None and _deps.retry_handler.can_retry and state.has_output():
                try:
                    async for rtipo, rtoken in _deps.retry_handler.attempt_recovery(
                        history, state.full_content, state.full_reasoning, model, session_id,
                    ):
                        state.append(rtipo, rtoken)
                        yield serialize_stream_event(rtipo, rtoken)
                    return
                except Exception as recover_err:
                    logger.error("Recovery also failed for %s: %s", session_id, recover_err)
            yield serialize_stream_event("error", {"type": error_type, "message": error_msg})
            return
        finally:
            # Always enqueue background vectorization (even on disconnect)
            background_tasks.add_task(_vectorize_session, session_id, _orch_deps)

            if not state.persisted and state.has_output():
                logger.info("Saving partial message for session %s after stream interruption", session_id)
                if await _save_with_retry("interruption"):
                    state.mark_persisted(time.monotonic())
                else:
                    logger.warning("Could not save partial message for session %s", session_id)
    return generate


async def _vectorize_session(session_id: str, orchestrator_deps: OrchestratorDeps | None = None) -> None:
    """Background task: vectorize session exchanges (FASE 7 + FASE 2 pipeline).

    Runs the full pipeline per exchange:
      keywords → noise filter → embed → cluster → extract entities → link entities

    Reuses the repos connection pool instead of opening standalone connections.
    Fails silently — never blocks the stream response.

    Uses a per-session asyncio lock to prevent data races with concurrent
    delete_memory or delete_cascade operations for the same session_id.
    """
    if session_id not in _vectorize_locks:
        _vectorize_locks[session_id] = asyncio.Lock()
    lock = _vectorize_locks[session_id]
    async with lock:
        try:
            from src.api.repos import get_repos
            _vs = importlib.import_module("src.memory.vectorize_sessions").vectorize_session
            heuristic_mod = importlib.import_module("src.memory.clustering.heuristic")
            relations_mod = importlib.import_module("src.memory.clustering.relations")
            linker_mod = importlib.import_module("src.memory.entity.linker")
            resolve_memory_db_path = importlib.import_module("src.memory.memory_db_path").resolve_memory_db_path
            HeuristicClusterer = heuristic_mod.HeuristicClusterer
            flush_clusters_to_db = heuristic_mod.flush_clusters_to_db
            detect_relations = relations_mod.detect_relations
            flush_relations_to_db = relations_mod.flush_relations_to_db
            EntityLinker = linker_mod.EntityLinker
            flush_entities_to_db = linker_mod.flush_entities_to_db
            flush_entity_relations_to_db = linker_mod.flush_relations_to_db
            flush_entity_mentions_to_db = linker_mod.flush_entity_mentions_to_db

            repos = orchestrator_deps.repos if orchestrator_deps and orchestrator_deps.repos else get_repos()
            db_path = resolve_memory_db_path()
            clusterer = HeuristicClusterer()
            linker = EntityLinker()

            count, noise, mappings, _ = await _vs(
                session_id, clusterer=clusterer, repos=repos, linker=linker,
            )
            if count > 0:
                await flush_clusters_to_db(clusterer, db_path, mappings=mappings)
                cluster_dicts = [c.as_dict for c in clusterer.clusters.values()]
                relations = detect_relations(cluster_dicts)
                if relations:
                    await flush_relations_to_db(relations, db_path)

                await flush_entities_to_db(linker, db_path)
                await flush_entity_relations_to_db(linker, db_path)
                await flush_entity_mentions_to_db(linker, db_path)

                logger.info("Vectorized session %s: %d exchanges (%d noise, %d clusters, %d entities)",
                            session_id, count, noise, len(clusterer.clusters), len(linker.get_entities()))
        except Exception:
            logger.exception("Failed to vectorize session %s (non-fatal)", session_id)
        finally:
            _vectorize_locks.pop(session_id, None)
