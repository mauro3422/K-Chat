"""Integración del canal Telegram — componentes reales, API mockeada.

Mockea ``api.telegram.org`` (sendMessage, editMessage, sendAction)
pero usa las implementaciones reales de:

- TelegramRenderer
- StreamParser
- MessageManager
- RateLimiter
- CharSplitter
- TelegramErrorHandler

IMPORTANTE: todos los tests son ``async def`` con ``@pytest.mark.asyncio``
porque ``tests/conftest.py`` define un fixture autouse async que exige que
cada test sea recolectado por pytest-asyncio. Usar clases agrava el problema
con pytest 9, así que todo está a nivel de módulo.
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncGenerator
from unittest.mock import Mock

import httpx
import pytest

from channels.telegram.char_splitter import CharSplitter
from channels.telegram.error_handler import TelegramErrorHandler
from channels.telegram.message_manager import MessageManager
from channels.telegram.rate_limiter import RateLimiter
from channels.telegram.renderer import TelegramRenderer


# Override the async autouse fixture from tests/conftest.py that conflicts
# with pytest 9 + pytest-asyncio strict mode. This sync no-op fixture
# replaces the async ``setup_test_db``, preventing PytestRemovedIn9Warning.
@pytest.fixture(autouse=True)
def setup_test_db() -> None:
    pass


# ── Mock de la API de Telegram ──────────────────────────────────────────────


class MockTelegramAPI:
    """Simula api.telegram.org con respuestas coherentes.

    - message_ids incrementales empezando en 1000
    - Registra todos los sends/edits/actions para aserciones posteriores
    """

    def __init__(self) -> None:
        self._next_id = 1000
        self.sent_messages: list[dict] = []
        self.edited_messages: list[dict] = []
        self.sent_actions: list[dict] = []
        self._texts: dict[int, str] = {}

    def _fresh_id(self) -> int:
        self._next_id += 1
        return self._next_id

    async def send_message(
        self, chat_id: int, text: str, parse_mode: str = "",
    ) -> int | None:
        msg_id = self._fresh_id()
        self.sent_messages.append(dict(
            chat_id=chat_id, text=text, parse_mode=parse_mode,
            message_id=msg_id,
        ))
        self._texts[msg_id] = text
        return msg_id

    async def edit_message(
        self, chat_id: int, message_id: int, text: str, parse_mode: str = "",
    ) -> bool:
        self.edited_messages.append(dict(
            chat_id=chat_id, message_id=message_id,
            text=text, parse_mode=parse_mode,
        ))
        self._texts[message_id] = text
        return True

    async def send_action(self, chat_id: int, action: str = "typing") -> None:
        self.sent_actions.append(dict(chat_id=chat_id, action=action))


# ── Spy de RateLimiter ──────────────────────────────────────────────────────


class RateLimiterSpy(RateLimiter):
    """Wraps RateLimiter y registra llamadas para verificarlas sin depender
    de timing real."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.wait_calls: list[tuple[int, int]] = []
        self.record_calls: list[tuple[int, int]] = []

    async def wait_if_needed(self, chat_id: int, message_id: int) -> None:
        self.wait_calls.append((chat_id, message_id))
        return await super().wait_if_needed(chat_id, message_id)

    async def record_edit(self, chat_id: int, message_id: int) -> None:
        self.record_calls.append((chat_id, message_id))
        return await super().record_edit(chat_id, message_id)


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _gen(*chunks: str) -> AsyncGenerator[str, None]:
    """Async generator helper que yieldea strings etiquetados."""
    for c in chunks:
        yield c


def _make_renderer(mock_api: MockTelegramAPI, **overrides: object) -> TelegramRenderer:
    """Construye un TelegramRenderer con defaults sensibles para tests."""
    kwargs: dict = dict(
        api_client=mock_api,
        message_manager=overrides.get("message_manager", MessageManager()),
        rate_limiter=overrides.get("rate_limiter", RateLimiter(min_edit_interval=0.01)),
        char_splitter=overrides.get("char_splitter", CharSplitter()),
        error_handler=overrides.get("error_handler", TelegramErrorHandler()),
    )
    kwargs.update(overrides)
    return TelegramRenderer(**kwargs)


# ══════════════════════════════════════════════════════════════════════════════
# Tests de pipeline completo
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_reasoning_content_reasoning_three_messages():
    """reasoning → content → reasoning crea 3 mensajes distintos."""
    api = MockTelegramAPI()
    r = _make_renderer(api)
    await r.render_stream(12345, _gen(
        "__reasoning__:Let me think",
        "__content__:Here is the answer",
        "__reasoning__:Wait, reconsidering",
    ))
    assert [m["message_id"] for m in api.sent_messages] == [1001, 1002, 1003]
    assert len(api.edited_messages) == 0


@pytest.mark.asyncio
async def test_reasoning_edit_in_same_phase():
    """Misma fase de reasoning edita el mensaje existente."""
    api = MockTelegramAPI()
    r = _make_renderer(api)
    await r.render_stream(12345, _gen(
        "__reasoning__:First thought",
        "__reasoning__:Deeper reasoning",
    ))
    assert len(api.sent_messages) == 1
    assert len(api.edited_messages) == 1
    assert api.edited_messages[0]["message_id"] == 1001
    assert "Deeper" in api.edited_messages[0]["text"]


@pytest.mark.asyncio
async def test_content_edit_in_same_phase():
    """Misma fase de content edita el mensaje existente."""
    api = MockTelegramAPI()
    r = _make_renderer(api)
    await r.render_stream(12345, _gen(
        "__content__:Short answer",
        "__content__:Short answer with more detail",
    ))
    assert len(api.sent_messages) == 1
    assert len(api.edited_messages) == 1
    assert "more detail" in api.edited_messages[0]["text"]


@pytest.mark.asyncio
async def test_reasoning_tool_content_three_messages():
    """reasoning → tool → content crea 3 mensajes separados."""
    api = MockTelegramAPI()
    r = _make_renderer(api)
    await r.render_stream(12345, _gen(
        "__reasoning__:I need to search",
        "__tool__:web_search",
        "__content__:Found results",
    ))
    assert [m["message_id"] for m in api.sent_messages] == [1001, 1002, 1003]


@pytest.mark.asyncio
async def test_tool_resets_phases():
    """tool resetea las fases: reasoning post-tool es mensaje nuevo."""
    api = MockTelegramAPI()
    r = _make_renderer(api)
    await r.render_stream(12345, _gen(
        "__reasoning__:Before tool",
        "__tool__:search",
        "__content__:After tool content",
    ))
    assert api.sent_messages[2]["message_id"] == 1003


@pytest.mark.asyncio
async def test_error_ends_stream():
    """Error corta el stream y no procesa más chunks."""
    api = MockTelegramAPI()
    r = _make_renderer(api)
    await r.render_stream(12345, _gen(
        "__reasoning__:Let me process",
        "__error__:Something went wrong",
        "__content__:should not appear",
    ))
    assert len(api.sent_messages) == 2
    assert "Error" in api.sent_messages[1]["text"]
    texts = [m["text"] for m in api.sent_messages]
    assert not any("should not appear" in t for t in texts)


@pytest.mark.asyncio
async def test_long_content_split():
    """Texto >4000 chars se parte en múltiples mensajes."""
    api = MockTelegramAPI()
    r = _make_renderer(api)
    long_text = "word boundary " * 290  # ~4060 chars > 4000
    await r.render_stream(12345, _gen(f"__content__:{long_text}"))
    assert len(api.sent_messages) >= 2
    assert any(m["text"].startswith("📎") for m in api.sent_messages[1:])


@pytest.mark.asyncio
async def test_short_content_no_split():
    """Texto corto queda en un solo mensaje."""
    api = MockTelegramAPI()
    r = _make_renderer(api)
    await r.render_stream(12345, _gen("__content__:Hello"))
    assert len(api.sent_messages) == 1


@pytest.mark.asyncio
async def test_reasoning_display_prefix():
    """Mensajes de reasoning llevan prefijo '🤔 Pensando...'."""
    api = MockTelegramAPI()
    r = _make_renderer(api)
    await r.render_stream(12345, _gen("__reasoning__:Think step by step"))
    assert api.sent_messages[0]["text"] == "🤔 Pensando...\n\nThink step by step"


@pytest.mark.asyncio
async def test_tool_display_format():
    """Tool call se muestra con 🔧 y el nombre."""
    api = MockTelegramAPI()
    r = _make_renderer(api)
    await r.render_stream(12345, _gen("__tool__:web_search"))
    assert "🔧" in api.sent_messages[0]["text"]
    assert "web_search" in api.sent_messages[0]["text"]


@pytest.mark.asyncio
async def test_multiple_tools_separate_messages():
    """Múltiples tools crean mensajes separados."""
    api = MockTelegramAPI()
    r = _make_renderer(api)
    await r.render_stream(12345, _gen(
        "__tool__:search",
        "__tool__:calculator",
    ))
    assert len(api.sent_messages) == 2


@pytest.mark.asyncio
async def test_none_chunk_skipped():
    """Chunks None del adapter se saltan sin error."""
    api = MockTelegramAPI()
    r = _make_renderer(api)

    async def gen_with_none():
        yield "__content__:visible"
        yield None  # type: ignore[reportReturnType]
        yield "__content__: also visible"

    await r.render_stream(12345, gen_with_none())
    assert len(api.sent_messages) == 1
    assert len(api.edited_messages) == 1
    assert "also visible" in api.edited_messages[0]["text"]


@pytest.mark.asyncio
async def test_phase_tracking_in_message_manager():
    """Fases reasoning-content-reasoning usan índices distintos en el MM."""
    api = MockTelegramAPI()
    mm = MessageManager()
    r = _make_renderer(api, message_manager=mm)
    await r.render_stream(12345, _gen(
        "__reasoning__:R0",
        "__content__:C0",
        "__reasoning__:R1",
    ))
    assert mm.get_msg_id(12345, "reasoning", 0) == 1001
    assert mm.get_msg_id(12345, "content", 1) == 1002
    assert mm.get_msg_id(12345, "reasoning", 1) == 1003


@pytest.mark.asyncio
async def test_tool_resets_phase_in_message_manager():
    """Tool resetea fases anteriores en MessageManager."""
    api = MockTelegramAPI()
    mm = MessageManager()
    r = _make_renderer(api, message_manager=mm)
    await r.render_stream(12345, _gen(
        "__reasoning__:R0",
        "__tool__:search",
        "__reasoning__:R1",
    ))
    assert mm.get_msg_id(12345, "reasoning", 0) is None
    assert mm.get_msg_id(12345, "reasoning", 1) == 1003
    assert mm.get_tool_msg_id(12345, "call_1") == 1002


# ══════════════════════════════════════════════════════════════════════════════
# Tests de RateLimiter
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_rate_limiter_first_edit_no_wait():
    """Primer edit no tiene wait."""
    rl = RateLimiter(min_edit_interval=0.1)
    t0 = time.time()
    await rl.wait_if_needed(123, 1001)
    assert time.time() - t0 < 0.03


@pytest.mark.asyncio
async def test_rate_limiter_consecutive_edit_waits():
    """Segundo edit dentro del intervalo espera."""
    rl = RateLimiter(min_edit_interval=0.1)
    await rl.record_edit(123, 1001)
    t0 = time.time()
    await rl.wait_if_needed(123, 1001)
    assert time.time() - t0 >= 0.08


@pytest.mark.asyncio
async def test_rate_limiter_different_messages_no_interference():
    """Mensajes distintos no interfieren."""
    rl = RateLimiter(min_edit_interval=0.1)
    await rl.record_edit(123, 1001)
    t0 = time.time()
    await rl.wait_if_needed(123, 1002)
    assert time.time() - t0 < 0.03


@pytest.mark.asyncio
async def test_rate_limiter_different_chats_no_interference():
    """Chats distintos no interfieren."""
    rl = RateLimiter(min_edit_interval=0.1)
    await rl.record_edit(123, 1001)
    t0 = time.time()
    await rl.wait_if_needed(456, 1001)
    assert time.time() - t0 < 0.03


@pytest.mark.asyncio
async def test_rate_limiter_429_backoff_blocks():
    """429 backoff global bloquea edits."""
    rl = RateLimiter(min_edit_interval=0.01)
    rl._global_backoff[123] = time.time() + 2.0
    t0 = time.time()
    await rl.wait_if_needed(123, 9999)
    assert time.time() - t0 >= 1.9


@pytest.mark.asyncio
async def test_rate_limiter_429_other_chat_unaffected():
    """429 backoff de un chat no afecta a otro."""
    rl = RateLimiter(min_edit_interval=0.01)
    rl._global_backoff[123] = time.time() + 10.0
    t0 = time.time()
    await rl.wait_if_needed(456, 1001)
    assert time.time() - t0 < 0.03


@pytest.mark.asyncio
async def test_rate_limiter_handle_429_sets_backoff_immediately():
    """handle_429() setea backoff antes del sleep."""
    rl = RateLimiter(min_edit_interval=0.01)
    task = asyncio.create_task(rl.handle_429(123, retry_after=0))
    await asyncio.sleep(0.01)
    assert 123 in rl._global_backoff
    assert rl._global_backoff[123] > time.time() + 1.5
    task.cancel()


@pytest.mark.asyncio
async def test_rate_limiter_clear_chat_removes_state():
    """clear_chat() limpia todo el estado de un chat."""
    rl = RateLimiter(min_edit_interval=0.01)
    await rl.record_edit(123, 1001)
    await rl.record_edit(123, 1002)
    rl._global_backoff[123] = time.time() + 10
    rl.clear_chat(123)
    assert (123, 1001) not in rl._last_edit
    assert (123, 1002) not in rl._last_edit
    assert 123 not in rl._global_backoff


@pytest.mark.asyncio
async def test_renderer_invokes_rate_limiter():
    """El renderer llama al rate limiter durante edits."""
    api = MockTelegramAPI()
    spy = RateLimiterSpy(min_edit_interval=0.01)
    r = _make_renderer(api, rate_limiter=spy)
    await r.render_stream(12345, _gen(
        "__reasoning__:A",
        "__reasoning__:B",
    ))
    assert len(spy.wait_calls) >= 1
    assert len(spy.record_calls) >= 1
    for _, mid in spy.record_calls:
        assert mid == 1001


# ══════════════════════════════════════════════════════════════════════════════
# Tests de ErrorHandler (clasificación)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_error_429_rate_limit():
    """429 Too Many Requests → retry con wait_seconds."""
    eh = TelegramErrorHandler()
    resp = Mock(status_code=429)
    resp.text = '{"ok":false,"parameters":{"retry_after":5}}'
    resp.json.return_value = {"ok": False, "parameters": {"retry_after": 5}}
    error = httpx.HTTPStatusError("rate limited", request=Mock(), response=resp)
    action = await eh.classify(error)
    assert action.retry is True
    assert action.wait_seconds >= 5
    assert action.abort is False


@pytest.mark.asyncio
async def test_error_400_not_modified():
    """400 'message is not modified' → benigno."""
    eh = TelegramErrorHandler()
    resp = Mock(status_code=400)
    resp.text = "Bad Request: message is not modified"
    error = httpx.HTTPStatusError("not modified", request=Mock(), response=resp)
    action = await eh.classify(error)
    assert action.retry is False
    assert action.abort is False


@pytest.mark.asyncio
async def test_error_400_too_long():
    """400 'too long' → fallback_text."""
    eh = TelegramErrorHandler()
    resp = Mock(status_code=400)
    resp.text = "Bad Request: message is too long"
    error = httpx.HTTPStatusError("too long", request=Mock(), response=resp)
    action = await eh.classify(error)
    assert action.retry is False
    assert action.abort is False
    assert action.fallback_text is not None
    assert "truncated" in (action.fallback_text or "")


@pytest.mark.asyncio
async def test_error_400_cant_parse():
    """400 'can't parse entities' → retry plain text."""
    eh = TelegramErrorHandler()
    resp = Mock(status_code=400)
    resp.text = "Bad Request: can't parse entities"
    error = httpx.HTTPStatusError("can't parse", request=Mock(), response=resp)
    action = await eh.classify(error)
    assert action.retry is True


@pytest.mark.asyncio
async def test_error_401_unauthorized():
    """401 Unauthorized → retry."""
    eh = TelegramErrorHandler()
    resp = Mock(status_code=401)
    resp.text = "Unauthorized"
    error = httpx.HTTPStatusError("unauthorized", request=Mock(), response=resp)
    action = await eh.classify(error)
    assert action.retry is True


@pytest.mark.asyncio
async def test_error_403_forbidden():
    """403 Forbidden → abort."""
    eh = TelegramErrorHandler()
    resp = Mock(status_code=403)
    resp.text = "Forbidden: bot was blocked by the user"
    error = httpx.HTTPStatusError("forbidden", request=Mock(), response=resp)
    action = await eh.classify(error)
    assert action.abort is True
    assert action.retry is False


@pytest.mark.asyncio
async def test_error_404_not_found():
    """404 → benigno (no retry, no abort)."""
    eh = TelegramErrorHandler()
    resp = Mock(status_code=404)
    resp.text = "Not Found"
    error = httpx.HTTPStatusError("not found", request=Mock(), response=resp)
    action = await eh.classify(error)
    assert action.retry is False
    assert action.abort is False


@pytest.mark.asyncio
async def test_error_409_conflict():
    """409 Webhook conflict → retry."""
    eh = TelegramErrorHandler()
    resp = Mock(status_code=409)
    resp.text = "Conflict: webhook is set"
    error = httpx.HTTPStatusError("conflict", request=Mock(), response=resp)
    action = await eh.classify(error)
    assert action.retry is True


@pytest.mark.asyncio
async def test_error_timeout_retry():
    """Timeout de red → retry."""
    eh = TelegramErrorHandler()
    error = httpx.TimeoutException("Connection timed out")
    action = await eh.classify(error)
    assert action.retry is True
    assert action.wait_seconds > 0


@pytest.mark.asyncio
async def test_error_network_error_retry():
    """Error de red → retry."""
    eh = TelegramErrorHandler()
    error = httpx.NetworkError("Connection refused")
    action = await eh.classify(error)
    assert action.retry is True


@pytest.mark.asyncio
async def test_error_unknown_error_abort():
    """Error desconocido → abort."""
    eh = TelegramErrorHandler()
    error = ValueError("unexpected error")
    action = await eh.classify(error)
    assert action.abort is True
    assert action.retry is False


# ══════════════════════════════════════════════════════════════════════════════
# Tests de CharSplitter
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_char_splitter_empty_text():
    """Texto vacío → [""]."""
    cs = CharSplitter()
    assert cs.split("") == [""]


@pytest.mark.asyncio
async def test_char_splitter_short_text():
    """Texto corto → un solo chunk."""
    cs = CharSplitter()
    assert cs.split("Hello world") == ["Hello world"]


@pytest.mark.asyncio
async def test_char_splitter_exact_fit():
    """Texto exacto al límite → un chunk."""
    cs = CharSplitter()
    text = "A" * 4000
    assert cs.split(text) == [text]


@pytest.mark.asyncio
async def test_char_splitter_long_text_splits():
    """Texto largo se parte en chunks <= max_chars."""
    cs = CharSplitter()
    long = "word " * 3000
    chunks = cs.split(long, max_chars=100)
    assert len(chunks) >= 2
    assert all(len(c) <= 100 for c in chunks)


@pytest.mark.asyncio
async def test_char_splitter_no_word_boundary():
    """Texto sin espacios → hard split."""
    cs = CharSplitter()
    long = "a" * 5000
    chunks = cs.split(long, max_chars=100)
    assert len(chunks) >= 50
    assert all(len(c) == 100 for c in chunks[:-1])
    assert len(chunks[-1]) <= 100


@pytest.mark.asyncio
async def test_char_splitter_newline_preferred():
    """Newline es punto de split preferido."""
    cs = CharSplitter()
    text = ("A" * 100) + "\n" + ("B" * 100)
    chunks = cs.split(text, max_chars=150)
    assert len(chunks) == 2
    assert "A" in chunks[0]
    assert "B" in chunks[1]


@pytest.mark.asyncio
async def test_char_splitter_custom_max_chars():
    """max_chars custom sobreescribe el default."""
    cs = CharSplitter()
    text = "Hello world foo bar baz"
    chunks = cs.split(text, max_chars=10)
    assert len(chunks) >= 2
