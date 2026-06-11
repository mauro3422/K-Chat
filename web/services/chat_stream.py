import json
import logging
import time
from collections.abc import Callable, Generator
from typing import Any

from fastapi import BackgroundTasks

from src.api import chat_stream, auto_rename_session
from web.services.message_persister import save_assistant_message
from web.services.stream_error_classifier import classify_error

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 20
LOOP_WINDOW_SIZE = 10
LOOP_PHRASE_REPEATS = 3


class _LoopDetector:
    """Detect repeated tokens or phrases that indicate the model is stuck."""

    def __init__(self):
        self._recent_tokens: list[str] = []
        self._recent_text: str = ""

    def check(self, token: str) -> str | None:
        self._recent_tokens.append(token)
        if len(self._recent_tokens) > LOOP_WINDOW_SIZE:
            self._recent_tokens = self._recent_tokens[-LOOP_WINDOW_SIZE:]

        if len(self._recent_tokens) >= LOOP_WINDOW_SIZE:
            if len(set(self._recent_tokens)) == 1 and self._recent_tokens[0].strip():
                return f"Loop detectado: mismo token repetido {LOOP_WINDOW_SIZE} veces"

        self._recent_text += token
        if len(self._recent_text) > 2000:
            self._recent_text = self._recent_text[-1000:]

        for phrase_len in [50, 100, 200]:
            if len(self._recent_text) >= phrase_len * LOOP_PHRASE_REPEATS:
                phrase = self._recent_text[-phrase_len:]
                count = self._recent_text.count(phrase)
                if count >= LOOP_PHRASE_REPEATS and len(phrase.strip()) > 10:
                    return f"Loop detectado: frase de {phrase_len} chars repetida {count} veces"

        return None


def build_stream_generator(
    session_id: str,
    message: str,
    history: list[dict[str, Any]],
    model: str,
    background_tasks: BackgroundTasks
) -> Callable[..., Generator[str, None, None]]:
    """Builds the NDJSON generator for the chat stream."""
    def generate() -> Generator[str, None, None]:
        full_reasoning = ""
        full_content = ""
        debug_info = {}
        phases_output = []
        saved = False

        logger.info("Starting chat for session %s with model %s", session_id, model)

        loop_detector = _LoopDetector()
        last_yield_time = time.monotonic()
        last_save_time = time.monotonic()
        save_interval = 30

        try:
            for tipo, token in chat_stream(message, history, model, session_id=session_id, tagged=True, debug=debug_info, phases_output=phases_output):
                now = time.monotonic()

                if tipo == "heartbeat":
                    continue

                if tipo == "content":
                    loop_error = loop_detector.check(token)
                    if loop_error:
                        logger.warning("Loop detected for %s: %s", session_id, loop_error)
                        yield json.dumps({"t": "error", "d": {"type": "loop_detected", "message": loop_error}}) + "\n"
                        break

                if tipo == "reasoning":
                    full_reasoning += token
                elif tipo == "content":
                    full_content += token

                yield json.dumps({"t": tipo, "d": token}) + "\n"
                last_yield_time = now

                if now - last_save_time > save_interval and (full_content or full_reasoning):
                    try:
                        save_assistant_message(session_id, full_content, full_reasoning, phases_output, debug_info, model)
                        saved = True
                        last_save_time = now
                    except Exception as e:
                        logger.warning("Periodic save failed: %s", e)

            if not full_content and not full_reasoning:
                logger.warning("Empty response for session %s with model %s", session_id, model)
                yield json.dumps({"t": "error", "d": {"type": "empty_response", "message": "The model did not generate any content"}}) + "\n"
                return

            logger.info("Chat completed for session %s: %d chars content, %d chars reasoning", session_id, len(full_content), len(full_reasoning))

            save_assistant_message(session_id, full_content, full_reasoning, phases_output, debug_info, model)
            saved = True
            background_tasks.add_task(auto_rename_session, session_id, message, model)

        except Exception as e:
            error_type, error_msg = classify_error(str(e))
            logger.error("Stream error for %s: [%s] %s", session_id, error_type, error_msg)
            yield json.dumps({"t": "error", "d": {"type": error_type, "message": error_msg}}) + "\n"
            return
        finally:
            if not saved and (full_content or full_reasoning):
                logger.info("Saving partial message for session %s after stream interruption", session_id)
                try:
                    save_assistant_message(session_id, full_content, full_reasoning, phases_output, debug_info, model)
                    saved = True
                except Exception as e:
                    logger.error("Final save failed for %s: %s", session_id, e)

    return generate
