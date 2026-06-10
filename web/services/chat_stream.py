import json
import logging
from collections.abc import Callable, Generator
from typing import Any

from fastapi import BackgroundTasks

from src.api import chat_stream, auto_rename_session
from web.services.message_persister import save_assistant_message
from web.services.stream_error_classifier import classify_error

logger = logging.getLogger(__name__)


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

        try:
            for tipo, token in chat_stream(message, history, model, session_id=session_id, tagged=True, debug=debug_info, phases_output=phases_output):
                if tipo == "reasoning":
                    full_reasoning += token
                elif tipo == "content":
                    full_content += token
                yield json.dumps({"t": tipo, "d": token}) + "\n"

            # Stream completed normally
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
                save_assistant_message(session_id, full_content, full_reasoning, phases_output, debug_info, model)
                saved = True

    return generate
