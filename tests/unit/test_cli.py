import ast
from unittest.mock import patch, AsyncMock

import pytest

from src.cli import main


@pytest.fixture
def mock_deps():
    async def async_gen():
        yield "resp"

    mock_repos = AsyncMock()

    with (
        patch("src.cli.get_default_model", return_value="test-model") as m_model,
        patch("src.cli.init_db") as m_init_db,
        patch("src.cli.get_repos", return_value=mock_repos) as m_get_repos,
        patch("src.cli.chat_stream") as m_chat,
        patch("sys.stdout.reconfigure") as m_reconf,
    ):
        m_chat.return_value = async_gen()
        yield {
            "model": m_model,
            "init_db": m_init_db,
            "repos": mock_repos,
            "chat_stream": m_chat,
            "reconfigure": m_reconf,
        }


@pytest.mark.anyio
async def test_main_init_called(mock_deps):
    with patch("builtins.input", side_effect=EOFError):
        await main()
    mock_deps["model"].assert_called_once()
    mock_deps["init_db"].assert_called_once()
    mock_deps["reconfigure"].assert_called_once()


@pytest.mark.anyio
async def test_main_exit_on_eoferror(mock_deps):
    with (
        patch("builtins.input", side_effect=EOFError),
        patch("builtins.print") as m_print,
    ):
        await main()
    m_print.assert_any_call("\nChau.")


@pytest.mark.anyio
async def test_main_exit_on_keyboardinterrupt(mock_deps):
    with (
        patch("builtins.input", side_effect=KeyboardInterrupt),
        patch("builtins.print") as m_print,
    ):
        await main()
    m_print.assert_any_call("\nChau.")


@pytest.mark.anyio
async def test_main_exit_on_salir(mock_deps):
    with (
        patch("builtins.input", side_effect=["salir", EOFError]),
        patch("builtins.print") as m_print,
    ):
        await main()
    m_print.assert_any_call("Chau.")


@pytest.mark.anyio
async def test_main_exit_on_exit(mock_deps):
    with (
        patch("builtins.input", side_effect=["exit", EOFError]),
        patch("builtins.print") as m_print,
    ):
        await main()
    m_print.assert_any_call("Chau.")


@pytest.mark.anyio
async def test_main_skips_empty_input(mock_deps):
    with (
        patch("builtins.input", side_effect=["", "salir", EOFError]),
        patch("builtins.print"),
    ):
        await main()


@pytest.mark.anyio
async def test_main_forwards_clear_command(mock_deps):
    with (
        patch("builtins.input", side_effect=["/clear", "salir", EOFError]),
        patch("src.cli.handle_command", return_value=None) as m_handle,
    ):
        await main()
    m_handle.assert_called_once_with("/clear", [])


@pytest.mark.anyio
async def test_main_forwards_model_command(mock_deps):
    with (
        patch("builtins.input", side_effect=["/model gpt-4", "salir", EOFError]),
        patch("src.cli.handle_command", return_value="gpt-4") as m_handle,
    ):
        await main()
    m_handle.assert_called_once_with("/model gpt-4", [])


@pytest.mark.anyio
async def test_main_forwards_unknown_command(mock_deps):
    with (
        patch("builtins.input", side_effect=["/unknown", "salir", EOFError]),
        patch("src.cli.handle_command", return_value=None) as m_handle,
    ):
        await main()
    m_handle.assert_called_once_with("/unknown", [])


@pytest.mark.anyio
async def test_main_calls_chat_stream_for_text(mock_deps):
    with (
        patch("builtins.input", side_effect=["hello", "salir", EOFError]),
    ):
        await main()
    mock_deps["chat_stream"].assert_called_once()
    args, kwargs = mock_deps["chat_stream"].call_args
    assert args[0] == "hello"


@pytest.mark.anyio
async def test_main_saves_messages(mock_deps):
    with (
        patch("builtins.input", side_effect=["hello", "salir", EOFError]),
    ):
        await main()
    calls = mock_deps["repos"].messages.save_record.call_args_list
    assert len(calls) == 2
    # save_record is called with MessageRecord object as first arg
    assert calls[0][0][0].role == "user"
    assert calls[0][0][0].content == "hello"
    assert calls[1][0][0].role == "assistant"
    assert calls[1][0][0].content == "resp"


@pytest.mark.anyio
async def test_main_handles_chat_exception(mock_deps):
    mock_deps["chat_stream"].side_effect = Exception("boom")
    with (
        patch("builtins.input", side_effect=["hello", "salir", EOFError]),
        patch("src.cli.logger") as m_logger,
    ):
        await main()
    assert m_logger.error.call_count == 1
    args, _ = m_logger.error.call_args
    assert args[0] == "Error en chat_stream: %s"
    assert isinstance(args[1], Exception)
    assert str(args[1]) == "boom"


@pytest.mark.anyio
async def test_main_forwards_help_command(mock_deps):
    with (
        patch("builtins.input", side_effect=["/help", "salir", EOFError]),
        patch("src.cli.handle_command", return_value=None) as m_handle,
    ):
        await main()
    m_handle.assert_called_once_with("/help", [])


@pytest.mark.anyio
async def test_module_has_main_block():
    with open("src/cli.py") as f:
        tree = ast.parse(f.read())
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            if (isinstance(node.test, ast.Compare)
                    and isinstance(node.test.left, ast.Name)
                    and node.test.left.id == "__name__"):
                for c in node.test.comparators:
                    if isinstance(c, ast.Constant) and c.value == "__main__":
                        found = True
    assert found


@pytest.mark.anyio
async def test_salir_constants():
    from src.cli import SALIR
    assert "salir" in SALIR
    assert "exit" in SALIR
    assert "quit" in SALIR
    assert "/exit" in SALIR
    assert "bye" in SALIR
