import logging
import time
from collections.abc import Callable, Generator
from typing import Any

from fastapi import BackgroundTasks

from src.core import chat_stream
from src.background_tasks import auto_rename_session
from web.services.loop_detector import LoopDetector
from web.services.message_persister import save_assistant_message
from web.services.stream_error_classifier import classify_error
from web.services.stream_retry_handler import StreamRetryHandler
from web.services.stream_contract import serialize_stream_event

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 20


def build_stream_generator(
    session_id: str,
    message: str,
    history: list[dict[str, Any]],
    model: str,
    background_tasks: BackgroundTasks,
    loop_detector: LoopDetector | None = None,
    retry_handler: StreamRetryHandler | None = None,
    save_fn: Callable | None = None,
    rename_fn: Callable | None = None,
) -> Callable[..., Generator[str, None, None]]:
    """Builds the NDJSON generator for the chat stream."""
    def generate() -> Generator[str, None, None]:
        full_reasoning = ""
        full_content = ""
        debug_info = {}
        phases_output = []
        saved = False

        logger.info("Starting chat for session %s with model %s", session_id, model)

        def _save_with_retry(desc: str = "") -> bool:
            for attempt in range(2):
                try:
                    _save(session_id, full_content, full_reasoning, phases_output, debug_info, model)
                    logger.info("Save OK%s: %d chars", f" ({desc})" if desc else "", len(full_content))
                    return True
                except Exception as e:
                    logger.warning("Save failed%s (attempt %d/2): %s", f" ({desc})" if desc else "", attempt + 1, e)
                    if attempt == 0:
                        time.sleep(0.5)
            return False

        detector = loop_detector or LoopDetector()
        _save = save_fn or save_assistant_message
        _rename = rename_fn or auto_rename_session
        last_yield_time = time.monotonic()
        last_save_time = time.monotonic()
        save_interval = 30

        try:
            for tipo, token in chat_stream(message, history, model, session_id=session_id, tagged=True, debug=debug_info, phases_output=phases_output):
                now = time.monotonic()

                if tipo == "heartbeat":
                    yield serialize_stream_event("heartbeat", "")
                    continue

                if tipo == "content":
                    loop_error = detector.check(token)
                    if loop_error:
                        logger.warning("Loop detected for %s: %s", session_id, loop_error)

                        recovered = False
                        if retry_handler is not None and retry_handler.can_retry:
                            logger.info(
                                "Transparent recovery (attempt %d/%d) for %s",
                                retry_handler.retry_count + 1,
                                retry_handler.max_retries,
                                session_id,
                            )
                            try:
                                for rtipo, rtoken in retry_handler.attempt_recovery(
                                    history, full_content, full_reasoning,
                                    model, session_id,
                                ):
                                    if rtipo == "reasoning":
                                        full_reasoning += rtoken
                                    elif rtipo == "content":
                                        full_content += rtoken
                                    yield serialize_stream_event(rtipo, rtoken)
                                    recovered = True
                            except Exception as e:
                                logger.error("Recovery failed for %s: %s", session_id, e)

                        if not recovered:
                            yield serialize_stream_event("error", {"type": "loop_detected", "message": loop_error})

                        break  # Exit main stream regardless of recovery outcome

                if tipo == "reasoning":
                    full_reasoning += token
                elif tipo == "content":
                    full_content += token

                yield serialize_stream_event(tipo, token)
                last_yield_time = now

                if now - last_save_time > save_interval and (full_content or full_reasoning):
                    if _save_with_retry("periodic"):
                        saved = True
                        last_save_time = now

            if not full_content and not full_reasoning:
                logger.warning("Empty response for session %s with model %s", session_id, model)
                yield serialize_stream_event("error", {"type": "empty_response", "message": "The model did not generate any content"})
                return

            logger.info("Chat completed for session %s: %d chars content, %d chars reasoning", session_id, len(full_content), len(full_reasoning))

            if _save_with_retry("final"):
                saved = True
            background_tasks.add_task(_rename, session_id, message, model)

        except GeneratorExit:
            logger.info("Client disconnected for %s", session_id)
            return
        except Exception as e:
            error_type, error_msg = classify_error(e)
            logger.error("Stream error for %s: [%s] %s", session_id, error_type, error_msg)
            yield serialize_stream_event("error", {"type": error_type, "message": error_msg})
            return
        finally:
            if not saved and (full_content or full_reasoning):
                logger.info("Saving partial message for session %s after stream interruption", session_id)
                if _save_with_retry("interruption"):
                    saved = True
                else:
                    try:
                        yield serialize_stream_event("error", {"type": "save_failed", "message": "Message not saved"})
                    except Exception:
                        pass

    return generate
