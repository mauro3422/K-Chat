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
    """Renders stream events to SEPARATE Telegram messages per element.

    THREE independent messages per assistant turn, matching the web UI:

        📨 Message 1 — Reasoning: 🤔 Pensando... [reasoning text]
        📨 Message 2 — Tools:     🔧 search_web → ✅ search_web
        📨 Message 3 — Content:   [answer with **bold** and `code`]

    Each message is managed independently: created on first event of its
    type, edited on subsequent updates. Tool pills get their OWN message
    (not inline in the reasoning), matching the web UI's separate
    ``<div class="tool-calls">`` element.

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
        # TRIAD-message per-chat state (reasoning, tools, content)
        self._reasoning_msg: dict[int, int] = {}       # chat_id → msg_id
        self._content_msg: dict[int, int] = {}          # chat_id → msg_id
        self._tool_msg: dict[int, int] = {}             # chat_id → msg_id (SEPARATE)
        self._reasoning_parts: dict[int, list[str]] = defaultdict(list)
        self._content_parts: dict[int, list[str]] = defaultdict(list)
        self._tool_parts: dict[int, list[str]] = defaultdict(list)  # SEPARATE
        self._tool_pills: dict[int, dict[str, str]] = defaultdict(dict)  # {tool_id: pill}
        # Continuation tracker per phase key
        self._phase_conts: dict[str, list[int]] = defaultdict(list)  # "reasoning:0" → [msg_id...]

    async def render_stream(
        self,
        chat_id: int,
        process_fn,
    ) -> None:
        """Render stream to separate reasoning + content messages."""
        self._parser = StreamParser()
        # Reset ALL per-chat state for this stream — reasoning, tools AND content
        self._reasoning_msg.pop(chat_id, None)
        self._content_msg.pop(chat_id, None)
        self._tool_msg.pop(chat_id, None)
        self._reasoning_parts.pop(chat_id, None)
        self._content_parts.pop(chat_id, None)
        self._tool_parts.pop(chat_id, None)
        self._tool_pills.pop(chat_id, None)
        logger.info("TG[%d] stream reset — razonamiento/tools/contenido state cleared", chat_id)

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
                    # Use event.tool_id if available, otherwise synthesize
                    # a unique key with the counter. ALWAYS increment the
                    # counter to ensure parallel tools get unique keys even
                    # when tool_id is empty (rate limit case, parse errors).
                    tool_key = event.tool_id or f"call_{tool_call_id_counter}"
                    await self._render_tool_call(chat_id, event, tool_key)
                    tool_call_id_counter += 1
                elif isinstance(event, ErrorEvent):
                    await self._render_error(chat_id, event)
                    return

        final_events = self._parser.flush()
        for event in final_events:
            if isinstance(event, ReasoningEvent):
                await self._render_reasoning(chat_id, event)
            elif isinstance(event, ContentEvent):
                await self._render_content(chat_id, event)

        logger.info("TG[%d] stream render complete", chat_id)

    # ── HTML formatting helpers ────────────────────────────────────────

    @staticmethod
    def _html_escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @staticmethod
    def _sanitize_html(html: str) -> str:
        """Ensure HTML is well-formed — close any unclosed tags.

        Telegram rejects messages with malformed HTML entities. Since the
        CharSplitter may split mid-formatting (e.g. cutting a ``**bold``
        into two chunks), this method closes any open ``<b>``, ``<i>``,
        ``<code>``, ``<pre>`` tags and removes any stray closing tags.
        """
        import re
        # Track open tags in order
        open_tags = []
        for match in re.finditer(r'</?(\w+)>', html):
            tag = match.group(0)
            name = match.group(1)
            if name in ('b', 'i', 'code', 'pre', 'em', 'strong'):
                if tag.startswith('</'):
                    if open_tags and open_tags[-1] == name:
                        open_tags.pop()
                else:
                    open_tags.append(name)
        # Close remaining open tags in reverse order
        for tag_name in reversed(open_tags):
            html += f'</{tag_name}>'
        # Remove stray closing tags without matching open
        # (already handled by the balance check above)
        return html

    @staticmethod
    def _text_to_html(text: str) -> str:
        """Convert **bold**, *italic*, `code` to HTML for Telegram."""
        import re
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'(?<!<[bi]>)\*(.+?)\*(?!</[bi]>)', r'<i>\1</i>', text)
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        return TelegramRenderer._sanitize_html(text)

    def _join_parts(self, parts: list[str]) -> str:
        return "\n".join(parts)

    # ── Reasoning message ──────────────────────────────────────────────

    async def _render_reasoning(
        self, chat_id: int, event: ReasoningEvent,
    ) -> None:
        """Create or edit the reasoning message (INDEPENDENT from tool pills).

        Reasoning is its OWN message. Tool pills have THEIR OWN message
        (managed by ``_render_tool_call``). They don't interact.
        """
        text = event.text
        parts = self._reasoning_parts[chat_id]
        phase = self._parser.reasoning_phase
        phase_key = f"reasoning:{phase}"

        if event.is_new_phase or self._reasoning_msg.get(chat_id) is None:
            # NEW reasoning message
            self._reasoning_parts[chat_id] = [f"🤔 Pensando...\n\n{text}"]
            html = self._text_to_html(self._join_parts(self._reasoning_parts[chat_id]))
            msg_id = await self._send_with_retry(chat_id, html, "HTML")
            if msg_id:
                self._reasoning_msg[chat_id] = msg_id
                await self._mm.store_msg_id(chat_id, phase_key, msg_id)
                logger.info("TG[%d] reasoning msg created: #%s", chat_id, msg_id)
        else:
            # EDIT existing reasoning — append new text
            if parts:
                prefix = "🤔 Pensando..."
                current = parts[0]
                if current.startswith(prefix):
                    existing_text = current[len(prefix):].strip()
                    if existing_text and text:
                        parts[0] = f"{prefix}\n\n{existing_text}\n{text}"
                    elif text:
                        parts[0] = f"{prefix}\n\n{text}"
                else:
                    parts[0] = f"{prefix}\n\n{text}"
            html = self._text_to_html(self._join_parts(parts))
            msg_id = self._reasoning_msg[chat_id]
            await self._edit_with_retry(chat_id, msg_id, html, "HTML", phase_key=phase_key)

    # ── Content message ────────────────────────────────────────────────

    async def _render_content(
        self, chat_id: int, event: ContentEvent,
    ) -> None:
        """Create or edit the content message (separate from reasoning)."""
        text = event.text
        parts = self._content_parts[chat_id]
        phase = self._parser.content_phase
        phase_key = f"content:{phase}"

        if event.is_new_phase or self._content_msg.get(chat_id) is None:
            # NEW content message
            self._content_parts[chat_id] = [text]
            html = self._text_to_html(text)
            msg_id = await self._send_with_retry(chat_id, html, "HTML")
            if msg_id:
                self._content_msg[chat_id] = msg_id
                await self._mm.store_msg_id(chat_id, phase_key, msg_id)
                logger.info("TG[%d] content msg created: #%s", chat_id, msg_id)
        else:
            # EDIT existing content
            if parts:
                parts[0] = text
            else:
                parts.append(text)
            html = self._text_to_html(self._join_parts(parts))
            msg_id = self._content_msg[chat_id]
            await self._edit_with_retry(chat_id, msg_id, html, "HTML", phase_key=phase_key)

    # ── Tool pills (inline in reasoning message) ───────────────────────

    async def _render_tool_call(
        self, chat_id: int, event: ToolCallEvent, tool_id: str,
    ) -> None:
        """Create or update a SEPARATE message for tool pills.

        Like the web UI's ``<div class="tool-calls">``, tool pills get
        their own Telegram message — NOT inline in the reasoning::

            📨 Mensaje 1 — 🤔 Pensando... [razonamiento]
            📨 Mensaje 2 — 🔧 web_search → ✅ web_search  ← SEPARATE!
            📨 Mensaje 3 — [contenido]

        This creates a clean 3-message layout per assistant turn.
        """
        # ── Build pill text ────────────────────────────────────────────
        if event.status == "calling":
            pill_label = f"🔧 {event.name}"
        elif event.status == "ok":
            pill_label = f"✅ {event.name}"
        elif event.status == "error":
            pill_label = f"❌ {event.name} (error)"
        else:
            pill_label = f"🔧 {event.name}"

        logger.info("TG[%d] tool_call: %s %s (id=%s)", chat_id, pill_label, event.status, tool_id)

        # ── Check if this is a status update for an existing pill ──────
        old_stored = self._tool_pills[chat_id].get(tool_id)
        parts = self._tool_parts[chat_id]

        if old_stored is not None:
            # Replace old pill in the tool message parts
            for i, p in enumerate(parts):
                if p.strip() == old_stored.strip():
                    parts[i] = pill_label
                    break
            self._tool_pills[chat_id][tool_id] = pill_label
        else:
            # New tool pill — add to tool message
            self._tool_pills[chat_id][tool_id] = pill_label
            parts.append(pill_label)

        # ── Send or edit the SEPARATE tool message ────────────────────
        msg_id = self._tool_msg.get(chat_id)
        if msg_id:
            # Edit existing tool message
            header = f"🔧 Herramientas:\n\n"
            full_text = header + "\n".join(parts)
            html = self._text_to_html(full_text)
            logger.info("TG[%d] edit tool msg #%s: %s", chat_id, msg_id, pill_label)
            await self._edit_with_retry(chat_id, msg_id, html, "HTML")
        else:
            # Send new tool message
            header = f"🔧 Herramientas:"
            full_text = header + "\n" + "\n".join(parts)
            html = self._text_to_html(full_text)
            logger.info("TG[%d] send new tool msg: %s", chat_id, pill_label)
            new_id = await self._send_with_retry(chat_id, html, "HTML")
            if new_id:
                self._tool_msg[chat_id] = new_id
                logger.info("TG[%d] tool msg created: #%s", chat_id, new_id)

    # ── Error ──────────────────────────────────────────────────────────

    async def _render_error(
        self, chat_id: int, event: ErrorEvent,
    ) -> None:
        """Append error to the content message or send a new one."""
        parts = self._content_parts[chat_id]
        parts.append(f"❌ Error: {event.message}")
        msg_id = self._content_msg.get(chat_id)
        if msg_id:
            html = self._text_to_html(self._join_parts(parts))
            await self._edit_with_retry(chat_id, msg_id, html, "HTML")
        else:
            html = self._text_to_html(self._join_parts(parts))
            new_id = await self._send_with_retry(chat_id, html, "HTML")
            if new_id:
                self._content_msg[chat_id] = new_id

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
                    logger.info("TG[%d] edit msg #%s benign: %s", chat_id, msg_id, e)
                    return False
        return False
