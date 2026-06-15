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
from collections import defaultdict

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
    """Renders stream events to a single Telegram message per turn.

    Instead of creating separate messages for reasoning, tools, and
    content, this renderer accumulates everything into ONE message:

        🤔 Pensando...
        [reasoning text]

        🔧 search_web
        ✅ search_web

        [content text]

    Tool pills appear inline with status updates (🔧 → ✅ → ❌).
    The web UI receives the separate phases via WS events unaffected.

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
        # Per-chat state for the single-message-per-turn model
        self._main_msg: dict[int, int] = {}         # chat_id → message_id
        self._display_text: dict[int, list[str]] = defaultdict(list)  # chat_id → [parts...]
        self._tool_pills: dict[int, dict[str, str]] = defaultdict(dict)  # chat_id → {tool_id: "🔧 name"}
        self._has_reasoning: dict[int, bool] = defaultdict(bool)
        self._has_content: dict[int, bool] = defaultdict(bool)
        # Continuation tracker: prevents duplicate 📎 chunks on re-edit
        self._cont_msgs: dict[int, list[int]] = defaultdict(list)  # chat_id → [msg_id, ...]
        # Message counter: ensures each turn's main msg_id is stored uniquely
        # so _clear_chat_messages can find ALL messages, not just the last one.
        self._msg_counter: dict[int, int] = defaultdict(int)  # chat_id → count

    async def render_stream(
        self,
        chat_id: int,
        process_fn,  # async generator yielding tagged strings
    ) -> None:
        """Render an entire message stream to a single Telegram message.

        Args:
            chat_id: Telegram chat ID.
            process_fn: Async generator yielding tagged strings
                       (``__reasoning__:...``, ``__content__:...``,
                        ``__tool__:...``, ``__error__:...``).
        """
        self._parser = StreamParser()  # fresh parser per stream
        # Reset per-chat state for this stream
        self._main_msg.pop(chat_id, None)
        self._display_text.pop(chat_id, None)
        self._tool_pills.pop(chat_id, None)
        self._has_reasoning.pop(chat_id, None)
        self._has_content.pop(chat_id, None)
        self._cont_msgs.pop(chat_id, None)

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

    # ── Single main message management ──────────────────────────────────

    def _build_display(self, chat_id: int) -> str:
        """Build the full display text from accumulated parts."""
        return "\n".join(self._display_text.get(chat_id, []))

    async def _ensure_main_msg(self, chat_id: int, initial_text: str) -> tuple[int | None, bool]:
        """Create or return the main message ID for this chat.
        
        Returns ``(msg_id, was_created)`` where ``was_created`` is True
        if a new message was sent (caller can skip redundant edit).
        """
        existing = self._main_msg.get(chat_id)
        if existing is not None:
            return existing, False
        html_text = self._build_html(chat_id) if self._display_text.get(chat_id) else initial_text
        msg_id = await self._send_with_retry(chat_id, html_text, "HTML")
        if msg_id is not None:
            self._main_msg[chat_id] = msg_id
            # Persist with unique key so _clear_chat_messages can find ALL
            # messages, not just the last one (keys: "main:0", "main:1", ...)
            cnt = self._msg_counter[chat_id]
            self._msg_counter[chat_id] = cnt + 1
            await self._mm.store_msg_id(chat_id, f"main:{cnt}", msg_id)
            return msg_id, True
        return None, False

    @staticmethod
    def _html_escape(text: str) -> str:
        """Escape HTML special chars for Telegram's HTML parse_mode."""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _build_html(self, chat_id: int) -> str:
        """Build display text with basic HTML formatting for Telegram.

        Converts ``**bold**`` and ``*italic*`` to HTML tags so Telegram
        renders them with ``parse_mode="HTML"``. Falls back to plain text
        if conversion fails.
        """
        import re
        text = self._build_display(chat_id)
        # Escape HTML first, then apply formatting
        text = self._html_escape(text)
        # Convert **bold** → <b>bold</b>
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        # Convert *italic* → <i>italic</i> (but not inside <b> tags)
        text = re.sub(r'(?<!<[bi]>)\*(.+?)\*(?!</[bi]>)', r'<i>\1</i>', text)
        # Convert `code` → <code>code</code>
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        return text

    async def _update_main_msg(self, chat_id: int) -> bool:
        """Edit the main message with the current display text."""
        msg_id = self._main_msg.get(chat_id)
        if msg_id is None:
            return False
        text = self._build_html(chat_id)
        ok = await self._edit_with_retry(chat_id, msg_id, text, "HTML")
        # Also send/update continuation chunks for overflow text
        chunks = self._cs.split(text)
        if len(chunks) > 1:
            conts = self._cont_msgs[chat_id]
            for ci, extra in enumerate(chunks[1:]):
                cont_text = f"📎 {extra}"
                if ci < len(conts) and conts[ci]:
                    # Reuse existing continuation (edit, no duplicate)
                    await self._do_edit(chat_id, conts[ci], cont_text, "")
                else:
                    new_id = await self._do_send(chat_id, cont_text, "")
                    if new_id:
                        conts.append(new_id)
                        await self._mm.store_msg_id(chat_id, f"cont:{ci}", new_id)
        return ok

    # ── Individual event renderers (all use the same main message) ──────

    async def _render_reasoning(
        self, chat_id: int, event: ReasoningEvent,
    ) -> None:
        """Append/replace reasoning text in the main message."""
        text = event.text
        parts = self._display_text[chat_id]

        if not self._has_reasoning[chat_id]:
            # First reasoning — add header + text
            self._has_reasoning[chat_id] = True
            parts.append(f"🤔 Pensando...\n\n{text}")
        else:
            # Update reasoning — find and replace the reasoning part
            for i, p in enumerate(parts):
                if p.startswith("🤔 Pensando..."):
                    parts[i] = f"🤔 Pensando...\n\n{text}"
                    break

        msg_id, created = await self._ensure_main_msg(chat_id, self._build_display(chat_id))
        if msg_id and not created:
            await self._update_main_msg(chat_id)

    async def _render_content(
        self, chat_id: int, event: ContentEvent,
    ) -> None:
        """Append/replace content text in the main message."""
        text = event.text
        parts = self._display_text[chat_id]

        if not self._has_content[chat_id]:
            self._has_content[chat_id] = True
            parts.append(text)
        else:
            # Find and update the content part
            # Content is always the last non-tool part
            content_idx = -1
            for i in range(len(parts) - 1, -1, -1):
                if not parts[i].startswith("🔧") and not parts[i].startswith("✅") and not parts[i].startswith("❌"):
                    content_idx = i
                    break
            if content_idx >= 0:
                parts[content_idx] = text
            else:
                parts.append(text)

        msg_id, created = await self._ensure_main_msg(chat_id, self._build_display(chat_id))
        if msg_id and not created:
            await self._update_main_msg(chat_id)

    async def _render_tool_call(
        self, chat_id: int, event: ToolCallEvent, tool_id: str,
    ) -> None:
        """Append inline tool pill to the main message (🔧 → ✅ → ❌)."""
        # Build the pill text
        if event.status == "calling":
            pill = f"🔧 {event.name}"
        elif event.status == "ok":
            pill = f"✅ {event.name}"
        elif event.status == "error":
            pill = f"❌ {event.name} (error)"
        else:
            pill = f"🔧 {event.name}"

        parts = self._display_text[chat_id]

        # Check if this tool already has a pill in the display
        old_pill = self._tool_pills[chat_id].get(tool_id)
        if old_pill is not None:
            # Status update — replace old pill text in parts
            for i, p in enumerate(parts):
                if p.strip() == old_pill.strip():
                    parts[i] = pill
                    break
        else:
            # New tool — append pill
            self._tool_pills[chat_id][tool_id] = pill
            parts.append(pill)

        msg_id, created = await self._ensure_main_msg(chat_id, self._build_display(chat_id))
        if msg_id and not created:
            await self._update_main_msg(chat_id)

    async def _render_error(
        self, chat_id: int, event: ErrorEvent,
    ) -> None:
        """Append error to the main message."""
        parts = self._display_text[chat_id]
        parts.append(f"❌ Error: {event.message}")

        msg_id, created = await self._ensure_main_msg(chat_id, self._build_display(chat_id))
        if msg_id and not created:
            await self._update_main_msg(chat_id)

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
        phase_key: str | None = None,
    ) -> bool:
        """Edit a message with rate limiting and error handling.

        If ``phase_key`` is given (e.g. ``"reasoning:0"``), continuation
        chunks (overflow beyond 4000 chars) are tracked via MessageManager
        and REUSED/EDITED on subsequent flushes instead of being re-sent.
        """
        # Wait for rate limit
        await self._rl.wait_if_needed(chat_id, msg_id)

        # Split if too long
        chunks = self._cs.split(text)
        if len(chunks) > 1:
            ok = await self._do_edit(chat_id, msg_id, chunks[0], parse_mode)

            if phase_key and phase_key in (self._mm._state.get(chat_id) or {}):
                # Parse phase_type and phase_index from key (e.g. "reasoning:0")
                parts = phase_key.split(":", 1)
                ptype = parts[0]
                pidx = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                existing = self._mm.get_continuations(chat_id, ptype, pidx)

                for ci, extra in enumerate(chunks[1:]):
                    cont_text = f"📎 {extra}"
                    if ci < len(existing) and existing[ci]:
                        # Edit existing continuation (reuse — no duplicate)
                        await self._do_edit(chat_id, existing[ci], cont_text, parse_mode)
                    else:
                        # Send new continuation and track its ID
                        new_id = await self._do_send(chat_id, cont_text, parse_mode)
                        if new_id:
                            await self._mm.set_continuation(chat_id, ptype, pidx, new_id, ci)
            else:
                # Fallback: no phase tracking — send as before
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
                elif action.fallback_text:
                    # Send fallback text so the user knows something went wrong
                    await self._api.send_message(chat_id, action.fallback_text, "")
                    return False
                else:
                    # Benign (e.g. "message not modified")
                    return False
        return False
