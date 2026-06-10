"""
Stress test: aborto de stream + persistencia parcial.
"""

import json
from unittest.mock import patch, MagicMock


def _build_mock_bg_tasks():
    bg = MagicMock()
    bg.add_task = MagicMock()
    return bg


@patch("web.services.chat_stream.save_assistant_message")
@patch("web.services.chat_stream.chat_stream")
def test_generator_exit_saves_partial_message(mock_chat_stream, mock_save):
    from web.services.chat_stream import build_stream_generator

    mock_chat_stream.return_value = iter([
        ("reasoning", "Pensando..."),
        ("content", "Hola"),
        ("content", " mundo"),
    ])

    bg = _build_mock_bg_tasks()
    gen = build_stream_generator("ses-1", "Hola", [{"role": "system", "content": "test"}], "test-model", bg)()

    chunks = [next(gen) for _ in range(3)]
    data = [json.loads(c.strip()) for c in chunks]
    assert data[0] == {"t": "reasoning", "d": "Pensando..."}
    assert data[1] == {"t": "content", "d": "Hola"}
    assert data[2] == {"t": "content", "d": " mundo"}

    gen.close()

    mock_save.assert_called_once()
    args, kwargs = mock_save.call_args
    assert args[0] == "ses-1"
    assert "Hola mundo" in args[1]
    assert args[5] == "test-model"
    assert args[2] == "Pensando..."
    bg.add_task.assert_not_called()


@patch("web.services.chat_stream.save_assistant_message")
@patch("web.services.chat_stream.chat_stream")
def test_complete_stream_saves_and_renames(mock_chat_stream, mock_save):
    from web.services.chat_stream import build_stream_generator

    mock_chat_stream.return_value = iter([
        ("reasoning", "Ok"),
        ("content", "Respuesta final."),
    ])

    bg = _build_mock_bg_tasks()
    chunks = list(build_stream_generator("ses-2", "Test", [{"role": "system", "content": "test"}], "test-model", bg)())

    assert len(chunks) == 2
    data = [json.loads(c.strip()) for c in chunks]
    assert data[0] == {"t": "reasoning", "d": "Ok"}
    assert data[1] == {"t": "content", "d": "Respuesta final."}

    mock_save.assert_called_once()
    args, kwargs = mock_save.call_args
    assert args[0] == "ses-2"
    assert args[1] == "Respuesta final."
    assert args[5] == "test-model"

    bg.add_task.assert_called_once()
    rename_args = bg.add_task.call_args[0]
    assert rename_args[0].__name__ == "auto_rename_session"


@patch("web.services.chat_stream.save_assistant_message")
@patch("web.services.chat_stream.chat_stream")
def test_abort_before_any_content_no_save(mock_chat_stream, mock_save):
    from web.services.chat_stream import build_stream_generator

    mock_chat_stream.return_value = iter([])

    bg = _build_mock_bg_tasks()
    chunks = list(build_stream_generator("ses-3", "Test", [{"role": "system", "content": "test"}], "test-model", bg)())

    assert len(chunks) == 1
    data = json.loads(chunks[0].strip())
    assert data["t"] == "error"
    assert data["d"]["type"] == "empty_response"

    mock_save.assert_not_called()
    bg.add_task.assert_not_called()


@patch("web.services.chat_stream.save_assistant_message")
@patch("web.services.chat_stream.chat_stream")
def test_abort_with_reasoning_only_saves_reasoning(mock_chat_stream, mock_save):
    from web.services.chat_stream import build_stream_generator

    mock_chat_stream.return_value = iter([
        ("reasoning", "Analizando la consulta..."),
        ("reasoning", " Buscando información..."),
    ])

    bg = _build_mock_bg_tasks()
    gen = build_stream_generator("ses-4", "Test", [{"role": "system", "content": "test"}], "test-model", bg)()

    chunks = [next(gen) for _ in range(2)]
    data = [json.loads(c.strip()) for c in chunks]
    assert data[0] == {"t": "reasoning", "d": "Analizando la consulta..."}
    assert data[1] == {"t": "reasoning", "d": " Buscando información..."}

    gen.close()

    mock_save.assert_called_once()
    args, kwargs = mock_save.call_args
    assert args[0] == "ses-4"
    assert args[1] == ""
    assert args[2] == "Analizando la consulta... Buscando información..."


@patch("web.services.chat_stream.save_assistant_message")
@patch("web.services.chat_stream.chat_stream")
def test_second_stream_after_abort_works(mock_chat_stream, mock_save):
    from web.services.chat_stream import build_stream_generator

    mock_chat_stream.side_effect = [
        iter([("content", "Primera")]),
        iter([("content", "Segunda completa.")]),
    ]

    bg = _build_mock_bg_tasks()

    gen1 = build_stream_generator("ses-5", "Msg1", [{"role": "system", "content": "test"}], "m", bg)()
    next(gen1)
    gen1.close()

    assert mock_save.call_count == 1
    assert mock_save.call_args_list[0].args[1] == "Primera"

    gen2 = build_stream_generator("ses-5", "Msg2", [{"role": "system", "content": "test"}], "m", bg)()
    chunks = list(gen2)

    assert len(chunks) == 1
    assert json.loads(chunks[0].strip()) == {"t": "content", "d": "Segunda completa."}

    assert mock_save.call_count == 2
    assert mock_save.call_args_list[1].args[1] == "Segunda completa."
    assert bg.add_task.call_count == 1


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
