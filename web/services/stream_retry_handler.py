import logging
from collections.abc import AsyncGenerator, Callable
from typing import Any

logger = logging.getLogger(__name__)

CONTINUATION_INSTRUCTION = (
    "[System: The previous response was interrupted before completion. "
    "Error type: {error_type}. Error detail: {error_message}. "
    "Continue from the last confirmed checkpoint. Do not repeat completed work "
    "or rerun tools whose results are already present. You may use tools when "
    "they are still needed to finish the original request.]"
)

DEFAULT_MAX_RETRIES = 2


def build_continuation_instruction(
    error_type: str,
    error_message: str,
) -> str:
    return CONTINUATION_INSTRUCTION.format(
        error_type=error_type or "unknown",
        error_message=error_message or "not provided",
    )


class StreamRetryHandler:
    """Resume interrupted streams with the completed history and partial tail."""

    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        llm_chat_stream_fn: Callable | None = None,
    ):
        self.max_retries = max_retries
        self._llm_chat_stream_fn = llm_chat_stream_fn
        self.retry_count = 0

    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries

    def build_messages(
        self,
        history: list[dict[str, Any]],
        partial_content: str,
        partial_reasoning: str,
    ) -> list[dict[str, Any]]:
        messages = list(history)
        if partial_content.strip() or partial_reasoning.strip():
            partial: dict[str, Any] = {
                "role": "assistant",
                "content": partial_content or None,
            }
            if partial_reasoning:
                partial["reasoning_content"] = partial_reasoning
            messages.append(partial)
        return messages

    async def attempt_recovery(
        self,
        history: list[dict[str, Any]],
        partial_content: str,
        partial_reasoning: str,
        model: str,
        session_id: str | None = None,
        *,
        stream_fn: Callable | None = None,
        orchestrator_deps: Any | None = None,
        error_type: str = "unknown",
        error_message: str = "",
    ) -> AsyncGenerator[tuple[str, Any], None]:
        if not self.can_retry:
            logger.info("Retry limit reached for %s", session_id or "?")
            return

        self.retry_count += 1
        messages = self.build_messages(
            history,
            partial_content,
            partial_reasoning,
        )
        continuation = build_continuation_instruction(
            error_type,
            error_message,
        )

        try:
            if stream_fn is not None and orchestrator_deps is not None:
                # Keep the caller's history as the live recovery history so a
                # second interruption checkpoints work completed during this
                # retry too.
                history[:] = messages
                messages = history
                orchestrator_deps.is_continuation = True
                async for event in stream_fn(
                    continuation,
                    messages,
                    model,
                    deps=orchestrator_deps,
                ):
                    yield event
            else:
                messages.append({"role": "user", "content": continuation})
                chat_stream_fn = self._llm_chat_stream_fn
                if chat_stream_fn is None:
                    from src.api.llm_client import (
                        llm_chat_stream as chat_stream_fn,
                    )
                async for event in chat_stream_fn(
                    messages,
                    model,
                    tagged=True,
                    tool_calls_output=None,
                ):
                    yield event
            logger.info("Recovery succeeded for %s", session_id or "?")
        except Exception as exc:
            logger.error(
                "Recovery attempt failed for %s: %s",
                session_id or "?",
                exc,
            )
            return
