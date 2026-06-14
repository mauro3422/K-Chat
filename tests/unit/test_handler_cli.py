import pytest
from unittest.mock import AsyncMock
from unittest.mock import patch

from src.cli_commands import handle_command


@pytest.mark.anyio
async def test_handle_model_switch():
    history = []
    result = handle_command("/model gpt-4", history)
    assert result == "gpt-4"
    assert len(history) == 1
    assert history[0]["role"] == "system"
    assert "gpt-4" in history[0]["content"]


@pytest.mark.anyio
async def test_handle_model_switch_multiple_words():
    history = []
    result = handle_command("/model deepseek-chat", history)
    assert result == "deepseek-chat"


@pytest.mark.anyio
async def test_handle_model_shows_current():
    with patch("src.cli_commands.get_default_model", return_value="default-llm"):
        with patch("builtins.print") as m_print:
            result = handle_command("/model", [])
    assert result is None
    m_print.assert_any_call("Modelo actual: default-llm")


@pytest.mark.anyio
async def test_handle_model_no_args_extra_whitespace():
    with patch("src.cli_commands.get_default_model", return_value="def"):
        with patch("builtins.print"):
            result = handle_command("/model   ", [])
    assert result is None


@pytest.mark.anyio
async def test_handle_clear():
    history = [{"role": "user", "content": "hello"}]
    with patch("builtins.print") as m_print:
        result = handle_command("/clear", history)
    assert result is None
    assert len(history) == 0
    m_print.assert_any_call("Historial borrado.")


@pytest.mark.anyio
async def test_handle_help():
    with patch("builtins.print") as m_print:
        result = handle_command("/help", [])
    assert result is None
    m_print.assert_any_call("/model <modelo>   - Cambiar modelo")
    m_print.assert_any_call("/clear            - Limpiar historial")
    m_print.assert_any_call("/help             - Mostrar ayuda")


@pytest.mark.anyio
async def test_handle_unknown():
    with patch("builtins.print") as m_print:
        result = handle_command("/unknown", [])
    assert result is None
    m_print.assert_any_call("Comando desconocido: /unknown. Usá /help")


@pytest.mark.anyio
async def test_case_insensitive():
    history = []
    result = handle_command("/MODEL gpt-4", history)
    assert result == "gpt-4"

    history2 = []
    result2 = handle_command("/CLEAR", history2)
    assert result2 is None

    with patch("builtins.print"):
        result3 = handle_command("/HELP", [])
    assert result3 is None


@pytest.mark.anyio
async def test_extra_whitespace_around_command():
    history = []
    result = handle_command("  /model  gpt-4  ", history)
    assert result == "gpt-4"


@pytest.mark.anyio
async def test_handle_unknown_preserves_history():
    history = [{"role": "user", "content": "hello"}]
    with patch("builtins.print"):
        handle_command("/bad", history)
    assert len(history) == 1
