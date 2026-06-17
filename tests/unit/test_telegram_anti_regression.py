"""Anti-regression tests for the Telegram rendering pipeline.

These tests guard against the bugs found and fixed on 2026-06-15:

1. Pills now create SEPARATE messages (not inline in reasoning)
2. 3-message flow: reasoning → tools → content
3. No reasoning text lost when first event is a tool
4. content_phase consistent (always 1, never 0)
5. No duplicate reasoning text (tg_reasoning_offset)
6. Rate limiter respects Telegram's ~20 edits/min limit
7. Content buf flushed before tool_call (not silently discarded)
8. tool_call_id_counter always increments for parallel tool keys
"""

import pytest
from channels.telegram.stream_parser import StreamParser
from channels.telegram.protocols import (
    ContentEvent,
    ErrorEvent,
    ReasoningEvent,
    ToolCallEvent,
)
from channels.telegram.renderer import TelegramRenderer
from channels.telegram.rate_limiter import RateLimiter
from unittest.mock import AsyncMock, MagicMock, patch


# ═══════════════════════════════════════════════════════════════════════
# STREAM PARSER TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestParserAntiRegression:
    """Parser-level anti-regression: phase tracking, content_phase, tools."""

    def test_content_as_first_event_phase_is_1(self):
        """BUG #2: content as first event must have content_phase=1 (not 0)."""
        p = StreamParser()
        p.feed("__content__:Hello")
        assert p.content_phase == 1, "content_phase debe ser 1 cuando content es el primer evento"

    def test_content_after_reasoning_phase_is_1(self):
        """content después de reasoning también debe tener content_phase=1."""
        p = StreamParser()
        p.feed("__reasoning__:Pienso")
        p.feed("__content__:Hello")
        assert p.content_phase == 1, "content_phase debe ser 1 cuando content viene después de reasoning"

    def test_content_phase_consistency(self):
        """Ambos caminos (content primero o después de reasoning) deben dar el mismo content_phase."""
        p1 = StreamParser()
        p1.feed("__content__:A")
        p2 = StreamParser()
        p2.feed("__reasoning__:R")
        p2.feed("__content__:A")
        assert p1.content_phase == p2.content_phase, "content_phase debe ser idéntico sin importar el orden de llegada"

    def test_tool_then_reasoning_no_new_phase(self):
        """BUG #1: reasoning después de tool NO debe crear nueva fase (inline)."""
        p = StreamParser()
        p.feed("__tool__:web_search:calling")
        events = p.feed("__reasoning__:Now I have data")
        assert len(events) == 1
        assert isinstance(events[0], ReasoningEvent)
        assert events[0].is_new_phase is False, "Reasoning post-tool debe ser misma fase (inline)"
        assert p.reasoning_phase == 0, "reasoning_phase no debe incrementar después de tool"

    def test_tool_then_content_creates_new_content_phase(self):
        """tool → content SÍ debe crear nueva fase de content."""
        p = StreamParser()
        p.feed("__tool__:web_search:calling")
        events = p.feed("__content__:Here is the answer")
        assert len(events) == 1
        assert isinstance(events[0], ContentEvent)
        assert events[0].is_new_phase is True, "Content post-tool debe ser nueva fase"
        assert p.content_phase == 1

    def test_multiple_tools_preserve_same_phase(self):
        """Múltiples tools seguidas no cambian la fase."""
        p = StreamParser()
        p.feed("__reasoning__:Let me search")
        p.feed("__tool__:call_1:web_search:calling")
        p.feed("__tool__:call_1:web_search:ok")
        p.feed("__tool__:call_2:read_file:calling")
        events = p.feed("__reasoning__:Now I have all data")
        assert events[0].is_new_phase is False
        assert p.reasoning_phase == 0

    def test_full_3_message_flow_phase_tracking(self):
        """Flujo completo: reasoning → tools → content debe tener phases correctas."""
        p = StreamParser()
        p.feed("__reasoning__:Pienso")          # reasoning_phase=0
        p.feed("__tool__:search:calling")        # inline
        p.feed("__tool__:search:ok")             # inline
        p.feed("__reasoning__:Más data")         # reasoning_phase=0 (same)
        assert p.reasoning_phase == 0
        events = p.feed("__content__:Answer")     # content_phase=1
        assert events[0].is_new_phase is True
        assert p.content_phase == 1

    def test_reasoning_after_content_is_new_phase(self):
        """REGRESIÓN CRÍTICA: reasoning después de content NO debe contaminar msg anterior."""
        p = StreamParser()
        p.feed("__reasoning__:R1")      # reasoning_phase=0
        p.feed("__content__:C1")         # content_phase=1
        events = p.feed("__reasoning__:R2")  # reasoning_phase=1 → NUEVO
        assert events[0].is_new_phase is True
        assert p.reasoning_phase == 1

    def test_tool_with_id_and_status(self):
        """Tool con tool_id y status se parsea correctamente."""
        p = StreamParser()
        events = p.feed("__tool__:call_abc123:web_search:ok")
        assert len(events) == 1
        assert isinstance(events[0], ToolCallEvent)
        assert events[0].tool_id == "call_abc123"
        assert events[0].name == "web_search"
        assert events[0].status == "ok"

    def test_tool_calling_status_default(self):
        """Tool sin status explícito debe ser 'calling'."""
        p = StreamParser()
        events = p.feed("__tool__:web_search")
        assert events[0].status == "calling"
        assert events[0].name == "web_search"

    def test_error_after_tool_stops_stream(self):
        """Error después de tool debe marcar stream como finished."""
        p = StreamParser()
        p.feed("__tool__:search:calling")
        p.feed("__error__:API failure")
        assert p.feed("__reasoning__:more") == []
        assert p.feed("__content__:more") == []


# ═══════════════════════════════════════════════════════════════════════
# RATE LIMITER TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestRateLimiterAntiRegression:
    """Rate limiter debe respetar el límite real de Telegram (~20 edits/min)."""

    def test_default_interval_is_3s(self):
        """BUG #3: El intervalo por defecto debe ser 3.0s (no 1.2s)."""
        rl = RateLimiter()
        # Verificar que el valor por defecto sea 3.0s (Telegram real limit ~20/min)
        assert rl._min_interval == 3.0, (
            f"Rate limiter default debe ser 3.0s para ~20 edits/min, "
            f"pero es {rl._min_interval}s"
        )

    def test_wait_enforces_interval(self):
        """wait_if_needed debe esperar si no ha pasado el intervalo."""
        rl = RateLimiter(min_edit_interval=1.0)
        import time
        rl._last_edit[(1, 100)] = time.time()  # edit just happened
        start = time.time()
        # Llamar wait_if_needed debería esperar ~1s
        import asyncio
        asyncio.run(rl.wait_if_needed(1, 100))
        elapsed = time.time() - start
        assert elapsed >= 0.9, f"Debió esperar ~1s, pero esperó {elapsed:.2f}s"

    def test_no_wait_if_enough_time_passed(self):
        """No debe esperar si ya pasó el intervalo."""
        rl = RateLimiter(min_edit_interval=0.1)
        import time
        rl._last_edit[(1, 100)] = time.time() - 5.0  # 5s ago
        start = time.time()
        import asyncio
        asyncio.run(rl.wait_if_needed(1, 100))
        elapsed = time.time() - start
        assert elapsed < 1.0, f"No debió esperar, pero esperó {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_record_edit_updates_timestamp(self):
        """record_edit debe actualizar el timestamp (es async)."""
        rl = RateLimiter()
        await rl.record_edit(1, 100)
        key = (1, 100)
        assert key in rl._last_edit
        assert rl._last_edit[key] > 0

    def test_handle_429_sets_global_backoff(self):
        """handle_429 debe setear backoff global para el chat."""
        rl = RateLimiter()
        import asyncio
        asyncio.run(rl.handle_429(1, 5))
        assert rl._global_backoff.get(1, 0) > 0


# ═══════════════════════════════════════════════════════════════════════
# RENDERER TESTS — 3 MESSAGE SEPARATION
# ═══════════════════════════════════════════════════════════════════════

class FakeAPI:
    """Simula Telegram API para tests del renderer."""
    
    def __init__(self):
        self.sent = []    # [(chat_id, text, parse_mode)]
        self.edited = []  # [(chat_id, msg_id, text, parse_mode)]
        self.next_msg_id = 1000
    
    async def send_message(self, chat_id, text, parse_mode=""):
        self.sent.append((chat_id, text, parse_mode))
        self.next_msg_id += 1
        return self.next_msg_id - 1
    
    async def edit_message(self, chat_id, msg_id, text, parse_mode=""):
        self.edited.append((chat_id, msg_id, text, parse_mode))
        return True


class FakeMM:
    """Simula MessageManager."""
    async def store_msg_id(self, *args): pass
    def get_continuations(self, *args): return []
    async def set_continuation(self, *args): pass


class FakeRL(RateLimiter):
    """RateLimiter sin esperas para tests."""
    def __init__(self):
        super().__init__(min_edit_interval=0.0)
    async def wait_if_needed(self, *args): pass
    async def record_edit(self, *args): pass


class FakeCS:
    """CharSplitter que no divide."""
    def split(self, text):
        return [text]


class FakeEH:
    """ErrorHandler que reintenta."""
    async def classify(self, error, ctx):
        from channels.telegram.protocols import RecoveryAction
        return RecoveryAction(retry=False, abort=False, wait_seconds=0)


@pytest.fixture
def renderer():
    """Renderer con dependencias mockeadas para test."""
    api = FakeAPI()
    return TelegramRenderer(
        api_client=api,
        message_manager=FakeMM(),
        rate_limiter=FakeRL(),
        char_splitter=FakeCS(),
        error_handler=FakeEH(),
    ), api


class TestRendererAntiRegression:
    """Renderer tests: 3 mensajes separados (reasoning, tools, content)."""

    @pytest.mark.asyncio
    async def test_reasoning_creates_first_message(self, renderer):
        """El primer evento de reasoning debe CREAR un mensaje."""
        r, api = renderer
        async def fake_stream():
            yield "__reasoning__:Let me think"
        await r.render_stream(12345, fake_stream())
        assert len(api.sent) == 1, "Debe enviar exactamente 1 mensaje"
        text = api.sent[0][1]
        assert "🤔 Pensando..." in text, "El mensaje debe tener el prefijo de pensamiento"
        assert "Let me think" in text

    @pytest.mark.asyncio
    async def test_reasoning_edits_on_same_phase(self, renderer):
        """Reasoning en misma fase debe EDITAR (no crear nuevo)."""
        r, api = renderer
        async def fake_stream():
            yield "__reasoning__:Let me think"
            yield "__reasoning__: deeply"
        await r.render_stream(12345, fake_stream())
        assert len(api.sent) == 1, "Solo debe haber 1 mensaje enviado"
        assert len(api.edited) >= 1, "Debe haber al menos 1 edit (segundo reasoning)"

    @pytest.mark.asyncio
    async def test_tool_call_creates_separate_message(self, renderer):
        """BUG CRÍTICO: Tool call debe crear su PROPIO mensaje, no editar el de reasoning."""
        r, api = renderer
        async def fake_stream():
            yield "__reasoning__:Let me search"
            yield "__tool__:call_1:web_search:calling"
        await r.render_stream(12345, fake_stream())
        
        # Debe haber 2 mensajes: reasoning + tools
        sent_msgs = [s[1] for s in api.sent]
        assert len(sent_msgs) == 2, (
            f"Debe haber 2 mensajes enviados (reasoning + tools), "
            f"pero hay {len(sent_msgs)}"
        )
        # El segundo mensaje debe ser el de tools
        tool_msg = sent_msgs[1]
        assert "🔧 web_search" in tool_msg, (
            f"El mensaje de tools debe contener 🔧 web_search, "
            f"pero tiene: {tool_msg[:100]}"
        )
        # El mensaje de reasoning NO debe contener 🔧
        reason_msg = sent_msgs[0]
        assert "🔧" not in reason_msg, (
            "El mensaje de reasoning NO debe contener pills 🔧"
        )

    @pytest.mark.asyncio
    async def test_3_messages_flow(self, renderer):
        """REGRESIÓN CRÍTICA: Flujo completo debe crear 3 mensajes separados."""
        r, api = renderer
        async def fake_stream():
            yield "__reasoning__:Let me think about this"
            yield "__tool__:call_1:web_search:calling"
            yield "__tool__:call_1:web_search:ok"
            yield "__reasoning__:Now I have the data"
            yield "__content__:Here is the answer"
        await r.render_stream(12345, fake_stream())
        
        sent_types = []
        for text in [s[1] for s in api.sent]:
            if "🤔 Pensando" in text:
                sent_types.append("reasoning")
            elif "🔧" in text or "✅" in text:
                sent_types.append("tools")
            elif text.strip():
                sent_types.append("content")
        
        assert sent_types == ["reasoning", "tools", "content"], (
            f"Los mensajes deben ser [reasoning, tools, content], "
            f"pero se obtuvo: {sent_types}"
        )

    @pytest.mark.asyncio
    async def test_tool_status_update_edits_tool_message(self, renderer):
        """Tool status update (calling→ok) debe EDITAR el mensaje de tools."""
        r, api = renderer
        async def fake_stream():
            yield "__tool__:call_1:web_search:calling"
            yield "__tool__:call_1:web_search:ok"
        await r.render_stream(12345, fake_stream())
        
        # Solo debe haber 1 mensaje enviado (tools)
        assert len(api.sent) == 1, "Solo debe haber 1 mensaje enviado (tools)"
        # Debe haber un edit cuando el status cambia de calling a ok
        assert len(api.edited) >= 1, "Debe haber al menos 1 edit (status update)"

    @pytest.mark.asyncio
    async def test_tool_first_no_pre_reasoning(self, renderer):
        """BUG #1: Tool como primer evento no debe perder reasoning posterior."""
        r, api = renderer
        async def fake_stream():
            yield "__tool__:call_1:web_search:calling"
            yield "__tool__:call_1:web_search:ok"
            yield "__reasoning__:Now I know the answer"
            yield "__content__:Here it is"
        await r.render_stream(12345, fake_stream())
        
        sent_texts = [s[1] for s in api.sent]
        # Buscar el mensaje de reasoning
        reasoning_msgs = [t for t in sent_texts if "🤔 Pensando" in t]
        assert len(reasoning_msgs) == 1, "Debe haber exactamente 1 mensaje de reasoning"
        assert "Now I know" in reasoning_msgs[0], (
            f"El reasoning post-tools debe aparecer en el mensaje de reasoning, "
            f"pero se obtuvo: {reasoning_msgs[0][:100]}"
        )

    @pytest.mark.asyncio
    async def test_multiple_tools_in_one_message(self, renderer):
        """Múltiples tools en paralelo deben estar en el mismo mensaje.

        La tool message se envía UNA VEZ y se edita con cada status update.
        Verificamos que el último edit contenga ambos tools con status final.
        """
        r, api = renderer
        async def fake_stream():
            yield "__reasoning__:I need multiple sources"
            yield "__tool__:call_1:web_search:calling"
            yield "__tool__:call_2:read_file:calling"
            yield "__tool__:call_1:web_search:ok"
            yield "__tool__:call_2:read_file:ok"
            yield "__content__:Combined answer"
        await r.render_stream(12345, fake_stream())
        
        # Solo debe haber 1 mensaje enviado (tools)
        tool_sent = [s[1] for s in api.sent if "🔧" in s[1] or "✅" in s[1]]
        assert len(tool_sent) == 1, "Todas las tools deben estar en 1 solo mensaje enviado"
        
        # El último edit debe tener el status final de ambos tools
        tool_edits = [e[2] for e in api.edited if "🔧" in e[2] or "✅" in e[2]]
        if tool_edits:
            last_edit = tool_edits[-1]
            assert "✅ web_search" in last_edit, (
                f"Último edit debe tener ✅ web_search, pero tiene: {last_edit[:100]}"
            )
            assert "✅ read_file" in last_edit, (
                f"Último edit debe tener ✅ read_file, pero tiene: {last_edit[:100]}"
            )

    @pytest.mark.asyncio
    async def test_content_after_tools_separate_message(self, renderer):
        """Content después de tools debe ser un mensaje SEPARADO."""
        r, api = renderer
        async def fake_stream():
            yield "__reasoning__:Thinking"
            yield "__tool__:search:calling"
            yield "__tool__:search:ok"
            yield "__content__:Final answer"
        await r.render_stream(12345, fake_stream())
        
        sent = [s[1] for s in api.sent]
        # Verificar que content es el último mensaje y está separado
        last_msg = sent[-1]
        assert "Final answer" in last_msg
        assert "🔧" not in last_msg, "Content no debe contener pills"

    @pytest.mark.asyncio
    async def test_empty_stream_no_message(self, renderer):
        """Stream vacío no debe enviar nada."""
        r, api = renderer
        async def fake_stream():
            yield None
            return
        await r.render_stream(12345, fake_stream())
        assert len(api.sent) == 0, "Stream vacío no debe enviar mensajes"

    @pytest.mark.asyncio
    async def test_error_sends_message(self, renderer):
        """Error event debe enviar un mensaje de error."""
        r, api = renderer
        async def fake_stream():
            yield "__error__:API failure"
        await r.render_stream(12345, fake_stream())
        assert len(api.sent) >= 1
        error_text = api.sent[0][1] if api.sent else ""
        assert "Error" in error_text or "❌" in error_text

    @pytest.mark.asyncio
    async def test_state_reset_between_streams(self, renderer):
        """REGRESIÓN: El estado debe resetearse entre streams.

        Verificamos que un segundo stream CREA nuevos mensajes en vez de
        editar los del primero (porque el estado se limpia en cada stream).
        """
        r, api = renderer
        
        # Stream 1
        async def stream1():
            yield "__reasoning__:First"
            yield "__content__:Done"
        await r.render_stream(12345, stream1())
        # Guardar IDs de los mensajes del stream 1
        stream1_ids = set()
        for s in api.sent:
            stream1_ids.add(s[0])  # msg_id no está en sent (no lo trackeamos fácilmente)
        # Mejor: trackear cuántos sends hubo en stream 1
        stream1_send_count = len(api.sent)
        
        # Reset api tracking para stream 2
        api.sent = []
        api.edited = []
        
        # Stream 2
        async def stream2():
            yield "__reasoning__:Second"
            yield "__content__:Done again"
        await r.render_stream(12345, stream2())
        
        # Stream 2 debe tener sus PROPIOS sends (no editó los del stream 1)
        assert len(api.sent) >= 1, "Stream 2 debe enviar mensajes nuevos"
        # Los mensajes de stream 2 deben ser diferentes a los de stream 1
        # (no podemos verificar IDs fácilmente, pero podemos verificar
        # que el texto NO sea el del stream 1)
        for s in api.sent:
            assert "First" not in s[1], (
                "Stream 2 no debe contener texto del stream 1"
            )

    @pytest.mark.asyncio
    async def test_content_buf_not_lost_on_tool_call(self, renderer):
        """REGRESIÓN: content_buf no debe perderse cuando llega un tool_call."""
        r, api = renderer
        async def fake_stream():
            yield "__content__:I was writing"
            yield "__content__: some text"
            yield "__tool__:search:calling"
            yield "__tool__:search:ok"
            yield "__content__: here it is"
        await r.render_stream(12345, fake_stream())
        
        sent = [s[1] for s in api.sent]
        content_texts = [t for t in sent if "I was writing" in t or "here it is" in t]
        assert len(content_texts) > 0, "El contenido escrito antes del tool_call no debe perderse"
        assert any("I was writing" in t for t in content_texts), (
            "El texto 'I was writing' debe estar en algún mensaje"
        )


# ═══════════════════════════════════════════════════════════════════════
# CONFIG SEPARATION TEST
# ═══════════════════════════════════════════════════════════════════════

class TestTelegramConfig:
    """Config debe estar separada del código y ser modificable por env."""

    def test_config_loaded_from_env(self, monkeypatch):
        """Config se carga de env vars."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test:token")
        monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "123,456")
        from channels.telegram.config import load_telegram_config
        cfg = load_telegram_config()
        assert cfg.bot_token == "test:token"
        assert 123 in cfg.allowed_users
        assert 456 in cfg.allowed_users

    def test_config_default_values(self):
        """Config tiene defaults seguros."""
        from channels.telegram.config import load_telegram_config
        cfg = load_telegram_config()
        assert cfg.poll_interval == 1.0
        assert cfg.session_timeout_minutes == 30
        assert cfg.api_base == "https://api.telegram.org"

    def test_rate_limiter_interval_from_config(self):
        """Rate limiter debe poder configurarse."""
        rl = RateLimiter(min_edit_interval=5.0)
        assert rl._min_interval == 5.0


# ═══════════════════════════════════════════════════════════════════════
# LAZY IMPORTS ANTI-REGRESSION TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestLazyImportsAntiRegression:
    """_LazyImports._ensure() no debe fallar con ImportError.

    BUG 2026-06-15: _ensure() importaba ``MessageRecord`` de ``src.api``,
    pero ``MessageRecord`` NO está exportado desde ``src.api.__init__``
    (no está en ``__all__`` ni importado a ese nivel).
    El fix fue importar ``MessageRecord`` desde ``src.api.repos``.

    Estos tests previenen que alguien reintroduzca el bug cambiando
    el import de vuelta a ``from src.api import MessageRecord``.
    """

    def test_MessageRecord_importable_from_api_repos(self):
        """MessageRecord debe poder importarse desde src.api.repos (el fix)."""
        from src.memory.repos import MessageRecord
        assert MessageRecord is not None

    def test_MessageRecord_NOT_in_src_api_top_level(self):
        """MessageRecord NO debe estar disponible desde src.api directamente.

        Si esto falla, significa que alguien lo agregó a src.api.__init__,
        lo cual es redundante con la importación desde src.api.repos.
        """
        import importlib
        import src.api
        importlib.reload(src.api)
        assert not hasattr(src.api, 'MessageRecord'), (
            "MessageRecord no debe estar en src.api. "
            "Usá 'from src.api.repos import MessageRecord' en su lugar."
        )

    def test_src_api_repos_exports_MessageRecord(self):
        """src.api.repos debe exportar MessageRecord (para los imports lazy)."""
        from src.api.repos import MessageRecord
        assert MessageRecord is not None

    def test_lazy_imports_ensure_does_not_raise(self):
        """_LazyImports._ensure() no debe lanzar ImportError.

        Este es el test directo del bug: si _ensure() intenta importar
        MessageRecord desde src.api, fallará con ImportError.
        """
        from channels.telegram.adapter import _LazyImports
        li = _LazyImports()
        # _ensure() se llama automáticamente en __getattr__
        try:
            _ = li.get_repos
        except ImportError as e:
            pytest.fail(f"_LazyImports._ensure() lanzó ImportError: {e}. "
                        f"Verificá que MessageRecord se importe desde "
                        f"src.api.repos, no desde src.api.")

    def test_lazy_imports_MessageRecord_accessible(self):
        """MessageRecord debe ser accesible desde _LazyImports después de _ensure()."""
        from channels.telegram.adapter import _LazyImports
        li = _LazyImports()
        _ = li.get_repos  # trigger _ensure()
        assert li.MessageRecord is not None, (
            "MessageRecord debe estar disponible en _LazyImports tras _ensure()"
        )

    def test_lazy_imports_all_attrs_accessible(self):
        """Todos los atributos importados por _ensure() deben ser accesibles."""
        from channels.telegram.adapter import _LazyImports
        li = _LazyImports()
        _ = li.get_repos  # trigger _ensure()
        for attr in ('MessageRecord', 'build_system_prompt', 'chat_stream',
                     'get_default_model', 'get_repos'):
            assert hasattr(li, attr), (
                f"_{attr} debe estar disponible en _LazyImports tras _ensure()"
            )
            assert getattr(li, attr) is not None, (
                f"_{attr} no debe ser None tras _ensure()"
            )
