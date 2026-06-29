import pytest
from unittest.mock import AsyncMock
from unittest.mock import MagicMock, patch

from src.core.orchestrator_contract import OrchestratorDeps


@pytest.mark.anyio
async def test_orchestrator_deps_defaults_are_empty():
    deps = OrchestratorDeps()

    assert deps.repos is None
    assert deps.default_model_fn is None
    assert deps.llm_chat_fn is None
    assert deps.llm_chat_stream_fn is None
    assert deps.compress_fn is None
    assert deps.should_compress_fn is None


@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.services.history_service.HistoryService.compress_if_needed", new_callable=AsyncMock)
@patch("src.core.services.tool_execution_service.ToolExecutionService.execute")
@patch("src.core.services.history_service.HistoryService.get_system_prompt")
@pytest.mark.anyio
async def test_chat_stream_uses_orchestrator_dependency_bundle(
    mock_get_sp, mock_execute,
    mock_compress, mock_save_debug,
):
    from src.core.orchestrator import chat_stream

    async def empty_stream(*args, **kwargs):
        if False:
            yield
    mock_execute.return_value = empty_stream()

    history = [{"role": "system", "content": "test"}]
    default_model_fn = MagicMock(return_value="bundle-model")

    deps = OrchestratorDeps(default_model_fn=default_model_fn, repos=MagicMock())
    async for _ in chat_stream("hola", history, deps=deps, streaming=True):
        pass

    default_model_fn.assert_called_once()
    mock_execute.assert_called_once()
