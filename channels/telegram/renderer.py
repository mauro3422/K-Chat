"""Telegram renderer — orchestrates stream event rendering to Telegram messages.

This is the central piece that ties together all Lego components:

1. Receives tagged strings from the adapter (async generator)
2. Parses them into typed events via StreamParser
3. Tracks phases and message IDs via MessageManager
4. Makes API calls via TelegramAPIClient
5. Throttles edits via RateLimiter
6. Splits long texts via CharSplitter
7. Recovers from errors via ErrorHandler
"""

from __future__ import annotations

import logging

from channels.telegram.protocols import (
    CharSplitterProtocol,
    ContentEvent,
    ErrorHandlerProtocol,
    ErrorEvent,
    MessageManagerProtocol,
    RateLimiterProtocol,
    ReasoningEvent,
    TelegramAPIClientProtocol,
    ToolCallEvent,
)
from channels.telegram.stream_parser import StreamParser

logger = logging.getLogger(__name__)


class TelegramRenderer:
    """Renders stream events to Telegram messages.

    Usage::

        renderer = TelegramRenderer(api_client, message_manager, ...)
        await renderer.render_stream(chat_id, adapter.process_message(...))
    """

    def __init__(
        self,
        api_client: TelegramAPIClientProtocol,
        message_manager: MessageManagerProtocol,
        rate_limiter: RateLimiterProtocol,
        char_splitter: CharSplitterProtocol,
        error_handler: ErrorHandlerProtocol,
    ) -> None:
        self._api = api_client
        self._mm = message_manager
        self._rl = rate_limiter
        self._cs = char_splitter
        self._eh = error_handler
        self._parser = StreamParser()

    async def render_stream(
        self,
        chat_id: int,
        process_fn,  # async generator yielding tagged strings
    ) -> None:
        """Render an entire message stream to Telegram messages.

        Args:
            chat_id: Telegram chat ID.
            process_fn: Async generator yielding tagged strings
                       (``__reasoning__:...``, ``__content__:...``,
                        ``__tool__:...``, ``__error__:...``).
        """
        self._parser = StreamParser()  # fresh parser per stream
        tool_call_id_counter = 0

        async for chunk in process_fn:
            if chunk is None:
                continue

            events = self._parser.feed(chunk)

            for event in events:
                if isinstance(event, ReasoningEvent):
                    await self._render_reasoning(chat_id, event)

                elif isinstance(event, ContentEvent):
                    await self._render_content(chat_id, event)

                elif isinstance(event, ToolCallEvent):
                    await self._render_tool_call(
                        chat_id, event, event.tool_id or f"call_{tool_call_id_counter}",
                    )
                    if event.tool_id:
                        tool_call_id_counter += 1

                elif isinstance(event, ErrorEvent):
                    await self._render_error(chat_id, event)
                    return  # stream ends on error

        # Flush any remaining buffers
        final_events = self._parser.flush()
        for event in final_events:
            if isinstance(event, ReasoningEvent):
                await self._render_reasoning(chat_id, event)
            elif isinstance(event, ContentEvent):
                await self._render_content(chat_id, event)

        logger.info("TG[%d] stream render complete", chat_id)

    # ── Individual event renderers ──────────────────────────────────────

    async def _render_reasoning(
        self, chat_id: int, event: ReasoningEvent,
    ) -> None:
        """Render a reasoning event."""
        phase = self._parser.reasoning_phase
        text = event.text

        if event.is_new_phase:
            # Create new message
            display = f"🤔 Pensando...\n\n{text}"
            msg_id = await self._send_with_retry(
                chat_id, display, parse_mode="",
            )
            if msg_id is not None:
                self._mm.set_msg_id(chat_id, "reasoning", phase, msg_id)
                logger.info(
                    "TG[%d] NEW reasoning msg #%s (phase %d)",
                    chat_id, msg_id, phase,
                )
        else:
            # Edit existing message
            msg_id = self._mm.get_msg_id(chat_id, "reasoning", phase)
            if msg_id is not None:
                display = f"🤔 Pensando...\n\n{text}"
                await self._edit_with_retry(chat_id, msg_id, display, "")

    async def _render_content(
        self, chat_id: int, event: ContentEvent,
    ) -> None:
        """Render a content event."""
        phase = self._parser.content_phase

        if event.is_new_phase:
            # Create new message
            msg_id = await self._send_with_retry(
                chat_id, event.text, parse_mode="",
            )
            if msg_id is not None:
                self._mm.set_msg_id(chat_id, "content", phase, msg_id)
                logger.info(
                    "TG[%d] NEW content msg #%s (phase %d, %d chars)",
                    chat_id, msg_id, phase, len(event.text),
                )
        else:
            # Edit existing message
            msg_id = self._mm.get_msg_id(chat_id, "content", phase)
            if msg_id is not None:
                await self._edit_with_retry(
                    chat_id, msg_id, event.text, "",
                )

    async def _render_tool_call(
        self, chat_id: int, event: ToolCallEvent, tool_id: str,
    ) -> None:
        """Render a tool call notification."""
        # Reset message phases so next reasoning/content create NEW messages
        self._mm.reset_phases(chat_id)

        # Check if this tool already has a message (status update)
        existing = self._mm.get_tool_msg_id(chat_id, tool_id)
        if existing is not None:
            # Update existing tool message
            display = self._format_tool_status(event.name, event.status)
            await self._edit_with_retry(
                chat_id, existing, display, "Markdown",
            )
            return

        # New tool call — send message
        display = self._format_tool_status(event.name, event.status)
        msg_id = await self._send_with_retry(
            chat_id, display, parse_mode="Markdown",
        )
        if msg_id is not None:
            self._mm.set_tool_msg_id(chat_id, tool_id, msg_id)
            logger.info("TG[%d] tool msg #%s: %s", chat_id, msg_id, event.name)

    async def _render_error(
        self, chat_id: int, event: ErrorEvent,
    ) -> None:
        """Render an error message."""
        display = f"❌ Error: {event.message}"
        await self._send_with_retry(chat_id, display, parse_mode="")

    # ── Helper: format tool status ──────────────────────────────────────

    @staticmethod
    def _format_tool_status(name: str, status: str) -> str:
        if status == "calling":
            return f"🔧 *{name}*"
        if status == "ok":
            return f"✅ *{name}*"
        if status == "error":
            return f"❌ *{name}* (error)"
        return f"🔧 *{name}*"

    # ── Helper: send with retry + error classification ───────────────────

    async def _send_with_retry(
        self, chat_id: int, text: str, parse_mode: str = "",
    ) -> int | None:
        """Send a message with error handling. Returns msg_id or None."""
        # Split if too long
        chunks = self._cs.split(text)
        if len(chunks) > 1:
            # Send first chunk, tag subsequent ones as continuation
            first = await self._do_send(chat_id, chunks[0], parse_mode)
            for extra in chunks[1:]:
                await self._do_send(chat_id, f"📎 {extra}", parse_mode)
            return first

        return await self._do_send(chat_id, text, parse_mode)

    async def _do_send(
        self, chat_id: int, text: str, parse_mode: str = "",
    ) -> int | None:
        """Single send attempt with error classification."""
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                parse = parse_mode if parse_mode else None
                msg_id = await self._api.send_message(
                    chat_id, text, parse_mode=parse or "",
                )
                if msg_id is not None:
                    return msg_id
                # send_message returned None (API error, already logged)
                return None
            except Exception as e:
                action = await self._eh.classify(e, {"chat_id": chat_id})
                if action.retry and attempt < max_retries:
                    if action.wait_seconds > 0:
                        import asyncio
                        await asyncio.sleep(action.wait_seconds)
                    # If fallback is plain text, retry with no parse_mode
                    if parse_mode and "can't parse" in str(e).lower():
                        parse_mode = ""
                    continue
                elif action.fallback_text:
                    # Send fallback text and stop
                    await self._api.send_message(chat_id, action.fallback_text, "")
                    return None
                elif action.abort:
                    logger.error("TG[%d] abort on send: %s", chat_id, e)
                    return None
                else:
                    # Benign error, skip
                    logger.debug("TG[%d] benign send error: %s", chat_id, e)
                    return None
        return None

    async def _edit_with_retry(
        self, chat_id: int, msg_id: int, text: str, parse_mode: str = "",
    ) -> bool:
        """Edit a message with rate limiting and error handling."""
        # Wait for rate limit
        await self._rl.wait_if_needed(chat_id, msg_id)

        # Split if too long
        chunks = self._cs.split(text)
        if len(chunks) > 1:
            # Only the first chunk can be edited; subsequent ones are sent
            ok = await self._do_edit(chat_id, msg_id, chunks[0], parse_mode)
            for extra in chunks[1:]:
                await self._do_send(chat_id, f"📎 {extra}", parse_mode)
            return ok

        return await self._do_edit(chat_id, msg_id, text, parse_mode)

    async def _do_edit(
        self, chat_id: int, msg_id: int, text: str, parse_mode: str = "",
    ) -> bool:
        """Single edit attempt with rate limiting and error handling."""
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                await self._rl.wait_if_needed(chat_id, msg_id)
                ok = await self._api.edit_message(
                    chat_id, msg_id, text, parse_mode=parse_mode or "",
                )
                if ok:
                    await self._rl.record_edit(chat_id, msg_id)
                    return True
                return False
            except Exception as e:
                action = await self._eh.classify(e, {
                    "chat_id": chat_id,
                    "message_id": msg_id,
                })
                if action.retry and attempt < max_retries:
                    if action.wait_seconds > 0:
                        import asyncio
                        await asyncio.sleep(action.wait_seconds)
                    # Switch to plain text on parse errors
                    if parse_mode and "can't parse" in str(e).lower():
                        parse_mode = ""
                    continue
                elif action.abort:
                    logger.error("TG[%d] abort on edit msg #%s: %s", chat_id, msg_id, e)
                    return False
                else:
                    # Benign (e.g. "message not modified")
                    return False
        return False
