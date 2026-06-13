from unittest.mock import MagicMock, patch

from src.core.orchestrator_contract import OrchestratorDeps


def test_orchestrator_deps_defaults_are_empty():
    deps = OrchestratorDeps()

    assert deps.repos is None
    assert deps.default_model_fn is None
    assert deps.llm_chat_fn is None
    assert deps.llm_chat_stream_fn is None
    assert deps.compress_fn is None
    assert deps.should_compress_fn is None


@patch("src.core.orchestrator._compress_if_needed")
@patch("src.core.orchestrator._save_debug_info")
@patch("src.core.orchestrator.run_tool_loop_streaming")
def test_chat_stream_uses_orchestrator_dependency_bundle(mock_loop_stream, mock_save_debug, mock_compress):
    from src.core.orchestrator import chat_stream

    mock_loop_stream.return_value = iter([])
    history = [{"role": "system", "content": "test"}]
    default_model_fn = MagicMock(return_value="bundle-model")

    deps = OrchestratorDeps(default_model_fn=default_model_fn)
    list(chat_stream("hola", history, deps=deps, streaming=True))

    default_model_fn.assert_called_once()
    mock_loop_stream.assert_called_once()
