"""Synchronous chat wrapper. Delegates to orchestrator.chat_stream()."""
from collections.abc import Generator
from typing import Any

from src.core import orchestrator


def chat(
    message_user: str,
    history: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Synchronous, non-streaming chat. Returns (response_text, updated_history).

    If history is None, a fresh system prompt is auto-generated.
    """
    if history is None:
        history = []

    tokens: list[str] = []
    for event in orchestrator.chat_stream(message_user, history, streaming=False, tagged=False):
        if isinstance(event, str):
            tokens.append(event)

    response = "".join(tokens)
    return response, history
