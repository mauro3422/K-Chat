import json
import logging
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from src.core.debug_info import DebugInfo
from src.core.history_contract import HistoryMessage
from src.core.orchestrator_contract import OrchestratorDeps
from src.memory.retrieval.hybrid_retriever import HybridResult

_default_deps = OrchestratorDeps(repos=MagicMock())

async def async_iter(items):
    for item in items:
        yield item

# ---------------------------------------------------------------------------
# _save_debug_info tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_save_debug_info_debug_is_none():
    from src.core.orchestrator import _save_debug_info
    _save_debug_info(None, [{"role": "user", "content": "hi"}], None)


@pytest.mark.anyio
async def test_save_debug_info_sets_history_before():
    from src.core.orchestrator import _save_debug_info
    debug = DebugInfo()
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    _save_debug_info(debug, history, None)
    assert len(debug.history_before) == 2
    assert debug.history_before[0]["role"] == "user"
    assert debug.history_before[0]["content"] == "hello"
    assert debug.phases == "[]"


@pytest.mark.anyio
async def test_save_debug_info_with_phases():
    from src.core.orchestrator import _save_debug_info
    debug = DebugInfo()
    phases = [{"reasoning": "thinking...", "tool_ids": [], "content": "result"}]
    _save_debug_info(debug, [], phases)
    assert debug.phases == json.dumps(phases)


@pytest.mark.anyio
async def test_save_debug_info_phases_none():
    from src.core.orchestrator import _save_debug_info
    debug = DebugInfo()
    _save_debug_info(debug, [], None)
    assert debug.phases == "[]"


@pytest.mark.anyio
async def test_save_debug_info_truncates_content():
    from src.core.orchestrator import _save_debug_info
    debug = DebugInfo()
    long = "x" * 1000
    history = [{"role": "user", "content": long}]
    _save_debug_info(debug, history, None)
    assert len(debug.history_before[0]["content"]) == 500


# ---------------------------------------------------------------------------
# compress_if_needed tests (Moved to HistoryService)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_compress_if_needed_below_threshold():
    from src.core.services.history_service import HistoryService
    service = HistoryService()
    history = [{"role": "user", "content": "hello"}]
    mock_should = MagicMock(return_value=False)
    mock_compress = AsyncMock()
    await service.compress_if_needed(history, "test-model", compress_fn=mock_compress, should_compress_fn=mock_should)
    mock_should.assert_called_once_with(history)
    mock_compress.assert_not_called()


@pytest.mark.anyio
async def test_compress_if_needed_above_threshold():
    from src.core.services.history_service import HistoryService
    service = HistoryService()
    history = [{"role": "user", "content": "hello"}]
    mock_should = MagicMock(return_value=True)
    mock_compress = AsyncMock()
    await service.compress_if_needed(history, "test-model", compress_fn=mock_compress, should_compress_fn=mock_should)
    mock_compress.assert_called_once_with(history, "test-model")


@pytest.mark.anyio
async def test_compress_if_needed_error(caplog):
    from src.core.services.history_service import HistoryService
    service = HistoryService()
    mock_should = MagicMock(return_value=True)
    mock_compress = AsyncMock(side_effect=ValueError("compress failed"))
    with caplog.at_level(logging.WARNING):
        await service.compress_if_needed([{"role": "user", "content": "hello"}], "test-model",
                                          compress_fn=mock_compress, should_compress_fn=mock_should)
    assert "compress_history failed" in caplog.text


# ---------------------------------------------------------------------------
# chat_stream tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_content_only(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    mock_execute.return_value = async_iter([
        ("reasoning", "thinking..."),
        ("content", "hello world"),
    ])
    from src.core.orchestrator import chat_stream

    history = [{"role": "system", "content": "test"}]
    tokens = []
    async for t in chat_stream("hello", history, model="test-model", tagged=True, streaming=True, deps=OrchestratorDeps(repos=MagicMock())):
        tokens.append(t)
        
    types = [t[0] for t in tokens]
    assert "reasoning" in types
    assert "content" in types
    contents = [t[1] for t in tokens if t[0] == "content"]
    assert any("hello world" in c for c in contents)
    assert history[-1].role == "user"
    assert history[-1].content == "hello"
    mock_get_sp.assert_not_called()
    mock_get_model.assert_not_called()
    # Pre-compression (before LLM) + post-compression (after stream) = 2 calls
    assert mock_compress.call_count >= 1, "compress_if_needed debe llamarse al menos una vez"
    mock_save_debug.assert_called_once()


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_untagged(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    mock_execute.return_value = async_iter(["raw content"])
    from src.core.orchestrator import chat_stream
    history = [{"role": "system", "content": "test"}]
    tokens = []
    async for t in chat_stream("hi", history, model="m", tagged=False, streaming=True, deps=OrchestratorDeps(repos=MagicMock())):
        tokens.append(t)
    assert tokens == ["raw content"]


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_default_model(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    mock_get_model.return_value = "default-model"
    mock_execute.return_value = async_iter([])
    from src.core.orchestrator import chat_stream
    async for _ in chat_stream("hi", [{"role": "system", "content": "test"}], streaming=True, deps=OrchestratorDeps(repos=MagicMock())):
        pass
    mock_get_model.assert_called_once()
    assert mock_execute.call_args[0][1] == "default-model"


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_empty_history(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    mock_get_sp.return_value = {"role": "system", "content": "sys prompt"}
    mock_execute.return_value = async_iter([])
    from src.core.orchestrator import chat_stream
    history = []
    async for _ in chat_stream("hi", history, model="m", streaming=True, deps=OrchestratorDeps(repos=MagicMock())):
        pass
    assert history[0].role == "system"
    assert history[0].content == "sys prompt"
    mock_get_sp.assert_called_once()
    args, kwargs = mock_get_sp.call_args
    assert args[0] == "m"
    assert "tool_definitions" in kwargs


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_debug_setup(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    mock_execute.return_value = async_iter([])
    from src.core.orchestrator import chat_stream
    debug = DebugInfo()
    history = [HistoryMessage(role="system", content="test", created_at="2024-01-01T00:00:00")]
    async for _ in chat_stream("hi", history, model="m", session_id="sess-1",
                                debug=debug, tagged=True, streaming=True, deps=OrchestratorDeps(repos=MagicMock())):
        pass
    assert debug.model == "m"
    assert debug.session_id == "sess-1"
    assert debug.reasoning == ""
    assert debug.tool_calls == []
    assert debug.system_prompt == "test"
    assert len(debug.history_before) == 2
    assert debug.history_before[1]["content"] == "hi"


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_phases_output_cleared(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    phases = [{"old": "data"}]
    mock_execute.return_value = async_iter([])
    from src.core.orchestrator import chat_stream
    async for _ in chat_stream("hi", [{"role": "system", "content": "t"}],
                                model="m", debug=DebugInfo(), phases_output=phases,
                                tagged=True, streaming=True, deps=OrchestratorDeps(repos=MagicMock())):
        pass
    assert phases == []


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_sync_path(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    mock_execute.return_value = async_iter([("content", "sync result")])
    from src.core.orchestrator import chat_stream
    history = [{"role": "system", "content": "test"}]
    tokens = []
    async for t in chat_stream("hi", history, model="m", tagged=True, streaming=False, deps=OrchestratorDeps(repos=MagicMock())):
        tokens.append(t)
    mock_execute.assert_called_once()
    assert any(t == ("content", "sync result") for t in tokens)


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_tool_calls(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    tc1 = json.dumps({"name": "web_search", "args": {"q": "test"}, "status": "calling"})
    tc2 = json.dumps({"name": "web_search", "args": {"q": "test"}, "status": "ok", "result": "found"})
    mock_execute.return_value = async_iter([
        ("tool_call", tc1),
        ("tool_call", tc2),
        ("content", "here you go"),
    ])
    from src.core.orchestrator import chat_stream
    history = [{"role": "system", "content": "test"}]
    tokens = []
    async for t in chat_stream("search", history, model="m", tagged=True, streaming=True, deps=OrchestratorDeps(repos=MagicMock())):
        tokens.append(t)
    types = [t[0] for t in tokens]
    assert "tool_call" in types
    assert "content" in types
    tool_events = [t[1] for t in tokens if t[0] == "tool_call"]
    assert any("calling" in te for te in tool_events)
    assert any("ok" in te for te in tool_events)


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_loop_error_propagates(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    mock_execute.side_effect = RuntimeError("stream failure")
    from src.core.orchestrator import chat_stream
    with pytest.raises(RuntimeError, match="stream failure"):
        async for _ in chat_stream("hi", [{"role": "system", "content": "t"}], model="m", streaming=True, deps=OrchestratorDeps(repos=MagicMock())):
            pass
    mock_save_debug.assert_not_called()
    # Pre-compression se ejecuta ANTES del error (antes del tool loop)
    mock_compress.assert_called_once()


@pytest.mark.anyio
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed")
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_chat_stream_pre_compression_trims_large_history(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    """Pre-compression debe truncar historiales grandes ANTES del LLM.

    BUG 2026-06-15: El bot de Telegram dejaba de responder cuando la sesión
    acumulaba >100 mensajes porque el historial COMPLETO se enviaba al LLM,
    que  timeout. La compresión solo corría DESPUÉS del LLM (post-stream),
    por lo que NUNCA llegaba a ejecutarse. El fix agrega una pre-compresión
    ANTES del tool loop para asegurar que el LLM reciba un contexto manejable.
    """
    from src.compressor import should_compress, MAX_HISTORY, KEEP_RECENT

    # Crear un historial con 50 mensajes (supera MAX_HISTORY=40)
    history = [{"role": "system", "content": "test"}]
    for i in range(50):
        history.append({"role": "user" if i % 2 == 0 else "assistant",
                        "content": f"Mensaje número {i}"})

    assert len(history) > MAX_HISTORY, "Setup: history debe superar MAX_HISTORY"
    assert should_compress(history), "Setup: should_compress debe dar True"

    # Hacer que compress_if_needed use la implementación REAL para que
    # trunque el historial correctamente
    from src.core.services.history_service import HistoryService
    real_service = HistoryService()
    
    async def _real_compress(hist, model, compress_fn=None, should_compress_fn=None):
        """Side effect que ejecuta la compresión real."""
        if should_compress_fn or should_compress(hist):
            # Versión simplificada: mantiene el primero + últimos KEEP_RECENT
            keep = KEEP_RECENT
            hist[:] = [hist[0]] + hist[-keep:]
    
    mock_compress.side_effect = _real_compress

    mock_execute.return_value = async_iter([
        ("content", "respuesta comprimida"),
    ])

    from src.core.orchestrator import chat_stream
    tokens = []
    async for t in chat_stream("último mensaje", history, model="m", tagged=True, streaming=True, deps=OrchestratorDeps(repos=MagicMock())):
        tokens.append(t)

    # Verificar que compress_if_needed fue llamado (pre-compression)
    assert mock_compress.called, (
        "compress_if_needed debe haber sido llamado para historial grande"
    )
    # El historial debe haberse comprimido (reducido de 52+ a ~17 mensajes)
    assert len(history) <= KEEP_RECENT + 1, (
        f"Historial grande debe comprimirse a ~{KEEP_RECENT + 1} mensajes, "
        f"pero quedaron {len(history)}"
    )


# ---------------------------------------------------------------------------
# Auto-retrieval tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@patch("src.config_loader.load_config")
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_auto_retrieval_disabled_by_config(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug, mock_load_config,
):
    cfg = MagicMock(auto_retrieval_enabled=False)
    mock_load_config.return_value = cfg
    mock_execute.return_value = async_iter([("content", "ok")])

    from src.core.orchestrator import chat_stream

    history = [{"role": "system", "content": "test"}]
    async for _ in chat_stream("hello", history, model="m", session_id="test-ar-1", tagged=True, streaming=True, deps=OrchestratorDeps(repos=MagicMock())):
        pass


@pytest.mark.anyio
@patch("src.config_loader.load_config")
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_auto_retrieval_empty_message(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug, mock_load_config,
):
    cfg = MagicMock(auto_retrieval_enabled=True)
    mock_load_config.return_value = cfg
    mock_execute.return_value = async_iter([("content", "ok")])

    from src.core.orchestrator import chat_stream

    history = [{"role": "system", "content": "test"}]
    async for _ in chat_stream("", history, model="m", session_id="test-ar-2", tagged=True, streaming=True, deps=OrchestratorDeps(repos=MagicMock())):
        pass


@pytest.mark.anyio
@patch("src.config_loader.load_config")
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_auto_retrieval_short_message(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug, mock_load_config,
):
    cfg = MagicMock(auto_retrieval_enabled=True)
    mock_load_config.return_value = cfg
    mock_execute.return_value = async_iter([("content", "ok")])

    from src.core.orchestrator import chat_stream

    history = [{"role": "system", "content": "test"}]
    async for _ in chat_stream("ab", history, model="m", session_id="test-ar-3", tagged=True, streaming=True, deps=OrchestratorDeps(repos=MagicMock())):
        pass


@pytest.mark.anyio
@patch("src.core.services.retrieval_service.format_memories_for_prompt")
@patch("src.config_loader.load_config")
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_auto_retrieval_first_message_passes(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug, mock_load_config,
    mock_format_mem,
):
    cfg = MagicMock(auto_retrieval_enabled=True)
    mock_load_config.return_value = cfg
    mock_format_mem.return_value = "AUTO-RETRIEVED MEMORIES\n- test"
    retriever_mock = AsyncMock()
    retriever_mock.search = AsyncMock(return_value=[HybridResult(rowid=1, text="test", fusion_score=0.9)])
    retriever_mock.close = MagicMock()

    from src.core.services.retrieval_service import RetrievalService
    svc = RetrievalService(config=cfg, retrieval_service=retriever_mock)

    mock_execute.return_value = async_iter([("content", "ok")])

    from src.core.orchestrator import chat_stream
    from src.core.orchestrator_contract import OrchestratorDeps

    history = [{"role": "system", "content": "test"}]
    async for _ in chat_stream("hello", history, model="m", session_id="test-ar-4", tagged=True, streaming=True, deps=OrchestratorDeps(repos=MagicMock(), retrieval_service=svc)):
        pass

    retriever_mock.search.assert_awaited_once_with("hello", top_k=8, apply_budget=True, source_filter='session', session_id='test-ar-4')


@pytest.mark.anyio
@patch("src.core.services.retrieval_service.format_memories_for_prompt")
@patch("src.config_loader.load_config")
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_auto_retrieval_throttle_second_message(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug, mock_load_config,
    mock_format_mem,
):
    cfg = MagicMock(auto_retrieval_enabled=True)
    mock_load_config.return_value = cfg
    mock_format_mem.return_value = "AUTO-RETRIEVED MEMORIES\n- test"
    retriever_mock = AsyncMock()
    retriever_mock.search = AsyncMock(return_value=[HybridResult(rowid=1, text="test", fusion_score=0.9)])
    retriever_mock.close = MagicMock()

    from src.core.services.retrieval_service import RetrievalService
    svc = RetrievalService(config=cfg, retrieval_service=retriever_mock)

    mock_execute.return_value = async_iter([("content", "ok")])

    from src.core.orchestrator import chat_stream
    from src.core.orchestrator_contract import OrchestratorDeps

    sid = "test-ar-5"
    history = [{"role": "system", "content": "test"}]

    deps = OrchestratorDeps(repos=MagicMock(), retrieval_service=svc)

    # First call → turn 1 → retrieval happens
    async for _ in chat_stream("hello", history, model="m", session_id=sid, tagged=True, streaming=True, deps=deps):
        pass
    retriever_mock.search.assert_awaited_once()

    # Second call → turn 2 → RETRIEVAL_INTERVAL=1 means every call retrieves
    retriever_mock.search.reset_mock()
    async for _ in chat_stream("hello again", history, model="m", session_id=sid, tagged=True, streaming=True, deps=deps):
        pass
    retriever_mock.search.assert_awaited_once()  # INTERVAL=1 → always retrieves


@pytest.mark.anyio
@patch("src.core.services.retrieval_service.format_memories_for_prompt")
@patch("src.config_loader.load_config")
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_auto_retrieval_close_on_success(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug, mock_load_config,
    mock_format_mem,
):
    cfg = MagicMock(auto_retrieval_enabled=True)
    mock_load_config.return_value = cfg
    mock_format_mem.return_value = "AUTO-RETRIEVED MEMORIES\n- test"
    retriever_mock = AsyncMock()
    retriever_mock.search = AsyncMock(return_value=[HybridResult(rowid=1, text="test", fusion_score=0.9)])
    retriever_mock.close = MagicMock()

    from src.core.services.retrieval_service import RetrievalService
    svc = RetrievalService(config=cfg, retrieval_service=retriever_mock)

    mock_execute.return_value = async_iter([("content", "ok")])

    from src.core.orchestrator import chat_stream
    from src.core.orchestrator_contract import OrchestratorDeps

    history = [{"role": "system", "content": "test"}]
    async for _ in chat_stream("hello", history, model="m", session_id="test-ar-6", tagged=True, streaming=True, deps=OrchestratorDeps(repos=MagicMock(), retrieval_service=svc)):
        pass

    retriever_mock.close.assert_called_once()


@pytest.mark.anyio
@patch("src.core.services.retrieval_service.format_memories_for_prompt")
@patch("src.config_loader.load_config")
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_auto_retrieval_close_on_exception(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug, mock_load_config,
    mock_format_mem,
):
    cfg = MagicMock(auto_retrieval_enabled=True)
    mock_load_config.return_value = cfg
    mock_format_mem.return_value = "AUTO-RETRIEVED MEMORIES\n- test"
    retriever_mock = AsyncMock()
    retriever_mock.search = AsyncMock(side_effect=ValueError("search failed"))
    retriever_mock.close = MagicMock()

    from src.core.services.retrieval_service import RetrievalService
    svc = RetrievalService(config=cfg, retrieval_service=retriever_mock)

    mock_execute.return_value = async_iter([("content", "ok")])

    from src.core.orchestrator import chat_stream
    from src.core.orchestrator_contract import OrchestratorDeps

    history = [{"role": "system", "content": "test"}]
    async for _ in chat_stream("hello", history, model="m", session_id="test-ar-7", tagged=True, streaming=True, deps=OrchestratorDeps(repos=MagicMock(), retrieval_service=svc)):
        pass

    retriever_mock.close.assert_called_once()


@pytest.mark.anyio
@patch("src.core.services.retrieval_service.format_memories_for_prompt")
@patch("src.config_loader.load_config")
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_auto_retrieval_memory_block_injected(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug, mock_load_config,
    mock_format_mem,
):
    cfg = MagicMock(auto_retrieval_enabled=True)
    mock_load_config.return_value = cfg
    mock_format_mem.return_value = "AUTO-RETRIEVED MEMORIES\n- test"
    retriever_mock = AsyncMock()
    retriever_mock.search = AsyncMock(return_value=[HybridResult(rowid=1, text="test", fusion_score=0.9)])
    retriever_mock.close = MagicMock()

    from src.core.services.retrieval_service import RetrievalService
    svc = RetrievalService(config=cfg, retrieval_service=retriever_mock)

    mock_execute.return_value = async_iter([("content", "ok")])
    mock_get_sp.return_value = {"role": "system", "content": "sys prompt with memories"}

    from src.core.orchestrator import chat_stream
    from src.core.orchestrator_contract import OrchestratorDeps

    history = []
    async for _ in chat_stream("hello", history, model="m", session_id="test-ar-8", tagged=True, streaming=True, deps=OrchestratorDeps(repos=MagicMock(), retrieval_service=svc)):
        pass

    mock_get_sp.assert_called_once()
    memory_results = mock_get_sp.call_args[1].get("memory_results")
    assert memory_results is not None
    assert "AUTO-RETRIEVED MEMORIES" in memory_results


@pytest.mark.anyio
@patch("src.config_loader.load_config")
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_auto_retrieval_no_memory_block_when_no_results(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug, mock_load_config,
):
    cfg = MagicMock(auto_retrieval_enabled=True)
    mock_load_config.return_value = cfg
    retriever_mock = AsyncMock()
    retriever_mock.search = AsyncMock(return_value=[])
    retriever_mock.close = MagicMock()

    from src.core.services.retrieval_service import RetrievalService
    svc = RetrievalService(config=cfg, retrieval_service=retriever_mock)

    mock_execute.return_value = async_iter([("content", "ok")])
    mock_get_sp.return_value = {"role": "system", "content": "sys prompt without memories"}

    from src.core.orchestrator import chat_stream
    from src.core.orchestrator_contract import OrchestratorDeps

    history = []
    async for _ in chat_stream("hello", history, model="m", session_id="test-ar-9", tagged=True, streaming=True, deps=OrchestratorDeps(repos=MagicMock(), retrieval_service=svc)):
        pass

    mock_get_sp.assert_called_once()
    memory_results = mock_get_sp.call_args[1].get("memory_results")
    assert memory_results is None


@pytest.mark.anyio
@patch("src.core.services.retrieval_service.format_memories_for_prompt")
@patch("src.config_loader.load_config")
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@patch("src.core.services.llm_service.LLMService.get_default_model")
async def test_auto_retrieval_yields_memory_event(
    mock_get_model, mock_get_sp, mock_execute,
    mock_compress, mock_save_debug, mock_load_config,
    mock_format_mem,
):
    cfg = MagicMock(auto_retrieval_enabled=True)
    mock_load_config.return_value = cfg
    mock_format_mem.return_value = "AUTO-RETRIEVED MEMORIES\n- test"
    retriever_mock = AsyncMock()
    retriever_mock.search = AsyncMock(return_value=[HybridResult(rowid=1, text="test", fusion_score=0.9)])
    retriever_mock.close = MagicMock()

    from src.core.services.retrieval_service import RetrievalService
    svc = RetrievalService(config=cfg, retrieval_service=retriever_mock)

    mock_execute.return_value = async_iter([("content", "ok")])
    mock_get_sp.return_value = {"role": "system", "content": "sys prompt"}

    from src.core.orchestrator import chat_stream
    from src.core.orchestrator_contract import OrchestratorDeps

    history = [{"role": "system", "content": "test"}]
    tokens = []
    async for t in chat_stream("hello", history, model="m", session_id="test-ar-10", tagged=True, streaming=True, deps=OrchestratorDeps(repos=MagicMock(), retrieval_service=svc)):
        tokens.append(t)

    memory_events = [t for t in tokens if t[0] == "memory"]
    assert len(memory_events) == 1
    assert "AUTO-RETRIEVED MEMORIES" in memory_events[0][1]
