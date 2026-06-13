import json
from unittest.mock import MagicMock, patch


def _bg_tasks():
    bg = MagicMock()
    bg.add_task = MagicMock()
    return bg


@patch("web.services.chat_stream.save_assistant_message")
@patch("web.services.chat_stream.chat_stream")
def test_loop_detection_recovery_streams_continuation(mock_chat_stream, mock_save):
    from web.services.chat_stream import build_stream_generator

    mock_chat_stream.return_value = iter([
        *[("content", "a") for _ in range(15)],
    ])

    retry_handler = MagicMock()
    retry_handler.can_retry = True
    retry_handler.attempt_recovery.return_value = iter([
        ("content", "recuperado"),
    ])

    bg = _bg_tasks()
    chunks = list(
        build_stream_generator(
            "sess-1",
            "mensaje",
            [{"role": "system", "content": "test"}],
            "model-x",
            bg,
            retry_handler=retry_handler,
        )()
    )

    parsed = [json.loads(chunk.strip()) for chunk in chunks]
    assert parsed[-1] == {"t": "content", "d": "recuperado"}
    retry_handler.attempt_recovery.assert_called_once()
    mock_save.assert_called_once()
    bg.add_task.assert_called_once()
