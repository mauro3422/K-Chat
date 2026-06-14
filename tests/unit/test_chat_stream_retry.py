import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


def _bg_tasks():
    bg = MagicMock()
    bg.add_task = MagicMock()
    return bg


@patch("web.services.chat_stream.save_assistant_message", new_callable=AsyncMock)
@patch("web.services.chat_stream.chat_stream")
@pytest.mark.anyio
async def test_loop_detection_recovery_streams_continuation(mock_chat_stream, mock_save):
    from web.services.chat_stream import build_stream_generator

    async def fake_stream(*a, **kw):
        for _ in range(15):
            yield ("content", "a")

    mock_chat_stream.side_effect = fake_stream

    retry_handler = MagicMock()
    retry_handler.can_retry = True
    
    async def fake_recovery(*a, **kw):
        yield ("content", "recuperado")
    
    retry_handler.attempt_recovery.side_effect = fake_recovery

    bg = _bg_tasks()
    gen_fn = build_stream_generator(
            "sess-1",
            "mensaje",
            [{"role": "system", "content": "test"}],
            "model-x",
            bg,
            retry_handler=retry_handler,
        )
    
    chunks = [t async for t in gen_fn()]

    parsed = [json.loads(chunk.strip()) for chunk in chunks]
    assert parsed[-1] == {"t": "content", "d": "recuperado"}
    retry_handler.attempt_recovery.assert_called_once()
    mock_save.assert_called()
    bg.add_task.assert_called_once()
