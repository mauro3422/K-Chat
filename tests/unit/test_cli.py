import ast
from unittest.mock import patch

import pytest

from src.cli import main


@pytest.fixture
def mock_deps():
    with (
        patch("src.cli.get_default_model", return_value="test-model") as m_model,
        patch("src.cli.init_db") as m_init_db,
        patch("src.cli.save_message_record") as m_save,
        patch("src.cli.chat_stream") as m_chat,
        patch("sys.stdout.reconfigure") as m_reconf,
    ):
        m_chat.return_value = iter(["resp"])
        yield {
            "model": m_model,
            "init_db": m_init_db,
            "save_message": m_save,
            "chat_stream": m_chat,
            "reconfigure": m_reconf,
        }


def test_main_init_called(mock_deps):
    with patch("builtins.input", side_effect=EOFError):
        main()
    mock_deps["model"].assert_called_once()
    mock_deps["init_db"].assert_called_once()
    mock_deps["reconfigure"].assert_called_once()


def test_main_exit_on_eoferror(mock_deps):
    with (
        patch("builtins.input", side_effect=EOFError),
        patch("builtins.print") as m_print,
    ):
        main()
    m_print.assert_any_call("\nChau.")


def test_main_exit_on_keyboardinterrupt(mock_deps):
    with (
        patch("builtins.input", side_effect=KeyboardInterrupt),
        patch("builtins.print") as m_print,
    ):
        main()
    m_print.assert_any_call("\nChau.")


def test_main_exit_on_salir(mock_deps):
    with (
        patch("builtins.input", side_effect=["salir", EOFError]),
        patch("builtins.print") as m_print,
    ):
        main()
    m_print.assert_any_call("Chau.")


def test_main_exit_on_exit(mock_deps):
    with (
        patch("builtins.input", side_effect=["exit", EOFError]),
        patch("builtins.print") as m_print,
    ):
        main()
    m_print.assert_any_call("Chau.")


def test_main_skips_empty_input(mock_deps):
    with (
        patch("builtins.input", side_effect=["", "salir", EOFError]),
        patch("builtins.print"),
    ):
        main()


def test_main_forwards_clear_command(mock_deps):
    with (
        patch("builtins.input", side_effect=["/clear", "salir", EOFError]),
        patch("src.cli.handle_command", return_value=None) as m_handle,
    ):
        main()
    m_handle.assert_called_once_with("/clear", [])


def test_main_forwards_model_command(mock_deps):
    with (
        patch("builtins.input", side_effect=["/model gpt-4", "salir", EOFError]),
        patch("src.cli.handle_command", return_value="gpt-4") as m_handle,
    ):
        main()
    m_handle.assert_called_once_with("/model gpt-4", [])


def test_main_forwards_unknown_command(mock_deps):
    with (
        patch("builtins.input", side_effect=["/unknown", "salir", EOFError]),
        patch("src.cli.handle_command", return_value=None) as m_handle,
    ):
        main()
    m_handle.assert_called_once_with("/unknown", [])


def test_main_calls_chat_stream_for_text(mock_deps):
    with (
        patch("builtins.input", side_effect=["hello", "salir", EOFError]),
    ):
        main()
    mock_deps["chat_stream"].assert_called_once()
    args, kwargs = mock_deps["chat_stream"].call_args
    assert args[0] == "hello"


def test_main_saves_messages(mock_deps):
    with (
        patch("builtins.input", side_effect=["hello", "salir", EOFError]),
    ):
        main()
    calls = mock_deps["save_message"].call_args_list
    assert len(calls) == 2
    # save_message_record is called with MessageRecord object as first arg
    assert calls[0][0][0].role == "user"
    assert calls[0][0][0].content == "hello"
    assert calls[1][0][0].role == "assistant"
    assert calls[1][0][0].content == "resp"


def test_main_handles_chat_exception(mock_deps):
    mock_deps["chat_stream"].side_effect = Exception("boom")
    with (
        patch("builtins.input", side_effect=["hello", "salir", EOFError]),
        patch("src.cli.logger") as m_logger,
    ):
        main()
    assert m_logger.error.call_count == 1
    args, _ = m_logger.error.call_args
    assert args[0] == "Error en chat_stream: %s"
    assert isinstance(args[1], Exception)
    assert str(args[1]) == "boom"


def test_main_forwards_help_command(mock_deps):
    with (
        patch("builtins.input", side_effect=["/help", "salir", EOFError]),
        patch("src.cli.handle_command", return_value=None) as m_handle,
    ):
        main()
    m_handle.assert_called_once_with("/help", [])


def test_module_has_main_block():
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


def test_salir_constants():
    from src.cli import SALIR
    assert "salir" in SALIR
    assert "exit" in SALIR
    assert "quit" in SALIR
    assert "/exit" in SALIR
    assert "bye" in SALIR
