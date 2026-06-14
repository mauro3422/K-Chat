import logging
import asyncio
import time
from collections.abc import Callable, AsyncGenerator
from typing import Any

from fastapi import BackgroundTasks

from src.api import (
    chat_stream,
    OrchestratorDeps,
    HistoryService,
    LLMService,
    ToolExecutionService,
    TelemetryService,
    DebugInfo,
    get_repos,
    auto_rename_session,
)
from web.services.loop_detector import LoopDetector
from web.services.message_persister import save_assistant_message
from web.services.stream_error_classifier import classify_error
from web.services.stream_retry_handler import StreamRetryHandler
from web.services.stream_contract import serialize_stream_event
from web.services.chat_stream_contract import StreamGeneratorDeps
from web.services.stream_state import StreamState

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 20


def build_stream_generator(
    session_id: str,
    message: str,
    history: list[dict[str, Any]],
    model: str,
    background_tasks: BackgroundTasks,
    chat_stream_fn: Callable[..., AsyncGenerator[Any, None]] | None = None,
    loop_detector: LoopDetector | None = None,
    retry_handler: StreamRetryHandler | None = None,
    save_fn: Callable | None = None,
    rename_fn: Callable | None = None,
    deps: StreamGeneratorDeps | None = None,
) -> Callable[..., AsyncGenerator[str, None]]:
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

        # Prepare orchestrator dependencies
        repos = get_repos()
        telemetry_service = TelemetryService()
        orchestrator_deps = OrchestratorDeps(
            repos=repos,
            history_service=HistoryService(repos=repos),
            telemetry_service=telemetry_service,
            llm_service=LLMService(telemetry_service=telemetry_service),
            tool_service=ToolExecutionService(),
            session_id=session_id,
            tagged=True,
            debug=debug_info,
            phases_output=phases_output,
            background_tasks=background_tasks
        )

        try:
            async for tipo, token in _chat_stream(message, history, model, deps=orchestrator_deps):
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
            logger.error("Stream error for %s: [%s] %s", session_id, error_type, error_msg)
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
            if not state.persisted and state.has_output():
                logger.info("Saving partial message for session %s after stream interruption", session_id)
                if await _save_with_retry("interruption"):
                    state.mark_persisted(time.monotonic())
                else:
                    logger.warning("Could not save partial message for session %s", session_id)

    return generate
