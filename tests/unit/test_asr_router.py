from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from web.routers.asr import _read_audio_payload, _transcribe_segment, asr_stream, router as asr_router


class _FakeRequest:
    def __init__(self, headers=None, body=b"", form=None):
        self.headers = headers or {}
        self._body = body
        self._form = form

    async def body(self):
        return self._body

    async def form(self):
        return self._form


@pytest.mark.anyio
async def test_read_audio_payload_from_raw_body():
    request = _FakeRequest(headers={"content-type": "application/octet-stream"}, body=b"wav-bytes")
    result = await _read_audio_payload(request)
    assert result == (b"wav-bytes", "application/octet-stream")


@pytest.mark.anyio
async def test_read_audio_payload_from_multipart_audio_file():
    upload = MagicMock()
    upload.read = AsyncMock(return_value=b"webm-bytes")
    upload.content_type = "audio/webm"
    request = _FakeRequest(
        headers={"content-type": "multipart/form-data; boundary=abc"},
        form={"audio": upload},
    )
    result = await _read_audio_payload(request)
    assert result == (b"webm-bytes", "audio/webm")
    upload.read.assert_awaited_once()


@pytest.mark.anyio
async def test_read_audio_payload_missing_audio_file():
    request = _FakeRequest(headers={"content-type": "multipart/form-data; boundary=abc"}, form={})
    with pytest.raises(HTTPException, match="Missing audio file"):
        await _read_audio_payload(request)


@pytest.mark.anyio
async def test_transcribe_segment_forwards_audio_and_content_type():
    with patch("web.routers.asr.transcribe_audio", new_callable=AsyncMock) as mocked:
        mocked.return_value = {"success": True, "transcript": "hola"}
        result = await _transcribe_segment(b"abc", content_type="audio/wav")

    assert result == {"success": True, "transcript": "hola"}
    mocked.assert_called_once_with(b"abc", content_type="audio/wav")


@pytest.mark.anyio
async def test_asr_routes_registered():
    paths = {route.path for route in asr_router.routes}
    assert "/api/asr/transcribe" in paths
    assert "/api/asr/stream" in paths


class _FakeWebSocket:
    def __init__(self, session_id="sess-1", messages=None):
        self.query_params = {"session_id": session_id}
        self._messages = messages or []
        self.sent_json = []
        self.accepted = False
        self.closed = False

    async def accept(self):
        self.accepted = True

    async def receive(self):
        if self._messages:
            return self._messages.pop(0)
        return {"type": "websocket.disconnect"}

    async def send_json(self, payload):
        self.sent_json.append(payload)

    async def close(self):
        self.closed = True


@pytest.mark.anyio
async def test_asr_websocket_stream_roundtrip():
    fake_ws = _FakeWebSocket(messages=[{"type": "websocket.receive", "bytes": b"wav-bytes"}])

    with patch("web.routers.asr._transcribe_segment", return_value={"success": True, "transcript": "hola"}), \
         patch("web.routers.asr._append_telemetry", new_callable=AsyncMock) as mock_telemetry:
        await asr_stream(fake_ws)

    assert fake_ws.accepted is True
    assert fake_ws.closed is True
    assert fake_ws.sent_json == [{"type": "transcript", "success": True, "transcript": "hola"}]
    mock_telemetry.assert_called_once()
    args, kwargs = mock_telemetry.call_args
    assert args[0] is fake_ws
    assert args[1] == "sess-1"
    assert args[2]["transport"] == "ws"
    assert args[2]["success"] is True
