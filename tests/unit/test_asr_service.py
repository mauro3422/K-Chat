import io
import os
import pytest
from unittest.mock import patch, MagicMock, mock_open, AsyncMock


@pytest.mark.anyio
async def test_transcribe_audio_empty():
    from web.services import asr_service

    result = await asr_service.transcribe_audio(b"")
    assert result["success"] is False
    assert "Empty or too small audio payload" in result["error"]


@pytest.mark.anyio
async def test_transcribe_audio_small():
    from web.services import asr_service

    result = await asr_service.transcribe_audio(b"small")
    assert result["success"] is False
    assert "Empty or too small audio payload" in result["error"]


@pytest.mark.anyio
async def test_transcribe_audio_conversion_fails():
    from web.services import asr_service

    with patch("web.services.asr_service._convert_to_wav", new_callable=AsyncMock) as mock_conv:
        mock_conv.return_value = None
        result = await asr_service.transcribe_audio(b"x" * 200)
        assert result["success"] is False
        assert "Invalid audio format" in result["error"]


@pytest.mark.anyio
async def test_transcribe_audio_invalid_wav():
    from web.services import asr_service

    with patch("web.services.asr_service._convert_to_wav", new_callable=AsyncMock) as mock_conv:
        mock_conv.return_value = b"invalid wav"
        with patch("wave.open", side_effect=Exception("Invalid WAV")):
            result = await asr_service.transcribe_audio(b"x" * 200)
            assert result["success"] is False
            assert "Cannot read converted audio" in result["error"]


@pytest.mark.anyio
async def test_transcribe_audio_success():
    from web.services import asr_service

    mock_recognizer = MagicMock()
    mock_recognizer.recognize_google = MagicMock(side_effect=lambda audio, language: {
        "es-AR": "transcripción en español",
        "en-US": "transcript in english"
    }.get(language, ""))

    mock_audio = MagicMock()

    with patch("web.services.asr_service._convert_to_wav", new_callable=AsyncMock) as mock_conv:
        mock_conv.return_value = b"valid wav"
        with patch("wave.open", MagicMock()):
            with patch("web.services.asr_service.sr.Recognizer", return_value=mock_recognizer):
                with patch("web.services.asr_service.sr.AudioFile") as mock_audio_file:
                    mock_audio_file.return_value.__enter__.return_value = mock_audio
                    result = await asr_service.transcribe_audio(b"x" * 200)

                    assert result["success"] is True
                    assert result["transcript"] == "transcripción en español"
                    assert result["transcript_es"] == "transcripción en español"
                    assert result["transcript_en"] == "transcript in english"


@pytest.mark.anyio
async def test_transcribe_audio_empty_after_conversion():
    from web.services import asr_service

    with patch("web.services.asr_service._convert_to_wav", new_callable=AsyncMock) as mock_conv:
        mock_conv.return_value = b"valid wav"
        with patch("wave.open") as mock_wave:
            mock_wf = MagicMock()
            mock_wf.getnframes.return_value = 0
            mock_wave.return_value.__enter__.return_value = mock_wf
            result = await asr_service.transcribe_audio(b"x" * 200)
            assert result["success"] is False
            assert "Empty audio" in result["error"]


@pytest.mark.anyio
async def test_convert_to_wav_ffmpeg_not_found():
    from web.services import asr_service

    with patch("tempfile.NamedTemporaryFile", MagicMock()):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = await asr_service._convert_to_wav(b"audio")
            assert result is None


@pytest.mark.anyio
async def test_convert_to_wav_success():
    from web.services import asr_service

    with patch("tempfile.NamedTemporaryFile") as mock_temp:
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.in"
        mock_temp.return_value.__enter__.return_value = mock_file

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = b""
            mock_run.return_value = mock_result

            with patch("builtins.open", mock_open(read_data=b"wav data")):
                result = await asr_service._convert_to_wav(b"audio")
                assert result == b"wav data"


@pytest.mark.anyio
async def test_ffmpeg_input_args_for_webm():
    from web.services import asr_service

    assert asr_service._ffmpeg_input_args("audio/webm;codecs=opus") == ["-f", "webm"]


@pytest.mark.anyio
async def test_ffmpeg_input_args_for_wav():
    from web.services import asr_service

    assert asr_service._ffmpeg_input_args("audio/wav") == ["-f", "wav"]


@pytest.mark.anyio
async def test_recognize_success():
    from web.services import asr_service

    mock_recognizer = MagicMock()
    mock_audio = MagicMock()

    with patch.object(mock_recognizer, "recognize_google", return_value="recognized text"):
        result = await asr_service._recognize(mock_recognizer, mock_audio, "es-AR")
        assert result == "recognized text"


@pytest.mark.anyio
async def test_recognize_unknown_value():
    from web.services import asr_service

    mock_recognizer = MagicMock()
    mock_audio = MagicMock()

    with patch.object(mock_recognizer, "recognize_google", side_effect=asr_service.sr.UnknownValueError):
        result = await asr_service._recognize(mock_recognizer, mock_audio, "es-AR")
        assert result == ""


@pytest.mark.anyio
async def test_recognize_request_error():
    from web.services import asr_service

    mock_recognizer = MagicMock()
    mock_audio = MagicMock()

    with patch.object(mock_recognizer, "recognize_google", side_effect=asr_service.sr.RequestError("API error")):
        result = await asr_service._recognize(mock_recognizer, mock_audio, "es-AR")
        assert result == ""


@pytest.mark.anyio
async def test_recognize_exception():
    from web.services import asr_service

    mock_recognizer = MagicMock()
    mock_audio = MagicMock()

    with patch.object(mock_recognizer, "recognize_google", side_effect=Exception("Unexpected error")):
        result = await asr_service._recognize(mock_recognizer, mock_audio, "es-AR")
        assert result == ""
