import logging
from collections.abc import Generator
from typing import Any

logger = logging.getLogger(__name__)

CONTINUATION_INSTRUCTION = (
    "[System: Your previous response was interrupted before completion. "
    "Continue from where you left off. Do NOT repeat anything you already wrote. "
    "Just continue naturally from the interruption point. Do NOT use tools.]"
)

DEFAULT_MAX_RETRIES = 2


class StreamRetryHandler:
    """Handles transparent recovery of interrupted LLM streams (e.g., loop detection).

    Decoupled from the stream generator — call ``attempt_recovery()`` whenever
    a stream needs to be restarted with continuation context.
    """

    def __init__(self, max_retries: int = DEFAULT_MAX_RETRIES):
        self.max_retries = max_retries
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
        """Build the message list for the continuation LLM call.

        Args:
            history: Full history up to (and including) the user message.
            partial_content: Content the model already generated.
            partial_reasoning: Reasoning the model already generated.

        Returns:
            Message list ready to pass to ``src.llm.client.chat_stream``.
        """
        messages = list(history)

        # Replay the partial assistant response so the model knows where it was
        combined = ""
        if partial_reasoning:
            combined += partial_reasoning + "\n\n"
        combined += partial_content
        if combined.strip():
            messages.append({"role": "assistant", "content": combined})

        # Continuation instruction as a user message
        messages.append({"role": "user", "content": CONTINUATION_INSTRUCTION})

        return messages

    def attempt_recovery(
        self,
        history: list[dict[str, Any]],
        partial_content: str,
        partial_reasoning: str,
        model: str,
        session_id: str | None = None,
    ) -> Generator[tuple[str, str], None, None]:
        """Try to recover by calling the LLM again with continuation context.

        Args:
            history: Full message history (system + user + tool results).
            partial_content: Text content generated before interruption.
            partial_reasoning: Reasoning text generated before interruption.
            model: Model name.
            session_id: Optional session ID for logging.

        Yields:
            ``(type, token)`` tuples (same format as ``chat_stream`` with ``tagged=True``).
            Yields nothing (immediately stops) if retry limit is exceeded or call fails.
        """
        if not self.can_retry:
            logger.info("Retry limit reached for %s, giving up", session_id or "?")
            return

        self.retry_count += 1
        logger.info(
            "Attempting recovery (attempt %d/%d) for %s",
            self.retry_count, self.max_retries, session_id or "?",
        )

        messages = self.build_messages(history, partial_content, partial_reasoning)

        try:
            from src.llm.client import chat_stream as llm_chat_stream

            # Only stream content — no tool calls for continuation
            for event in llm_chat_stream(
                messages,
                model,
                tagged=True,
                tool_calls_output=None,
            ):
                yield event

            logger.info(
                "Recovery succeeded for %s",
                session_id or "?",
            )
        except Exception as e:
            logger.error("Recovery attempt failed for %s: %s", session_id or "?", e)
            return
