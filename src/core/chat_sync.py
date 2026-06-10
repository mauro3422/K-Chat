from src.llm import get_default_model
from src.context import build_system_prompt
from src.core import _deps
from src.tools import TOOLS
from typing import Any


def chat(message_user: str, history: list[dict[str, Any]] | None = None) -> tuple[str, list[dict[str, Any]]]:
    """Processes a message with text and memory. Returns response and updated history."""
    model = get_default_model()
    if history is None:
        history = [build_system_prompt(model)]
    history.append({"role": "user", "content": message_user})
    choice = _deps.llm_chat(history, model, tools=TOOLS)
    response = choice.message.content or ""
    history.append({"role": "assistant", "content": response})
    return response, history
