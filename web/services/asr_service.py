"""ASR service — transcribe audio using Google Speech API.

Adapted from DuckSugar's transcribe_server.py to run inside K-Chat.
Supports WebM (MediaRecorder), WAV, and other formats via ffmpeg conversion.
"""

from __future__ import annotations

import io
import logging
import os
import subprocess
import tempfile
import wave
from concurrent.futures import ThreadPoolExecutor
import io
import logging
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import speech_recognition as sr

logger = logging.getLogger(__name__)

ASR_LANGUAGE = "es-AR"


def transcribe_audio(audio_data: bytes, language: str = ASR_LANGUAGE) -> dict[str, Any]:
    """Transcribe audio bytes using Google Speech API.

    Accepts any format supported by ffmpeg (WebM/Opus from MediaRecorder, WAV, etc.).
    Converts to WAV via ffmpeg before passing to speech_recognition.

    Args:
        audio_data: Raw audio bytes.
        language: Primary language hint (default: es-AR).

    Returns:
        dict with keys: success, transcript, transcript_es, transcript_en, error
    """
    if not audio_data or len(audio_data) < 100:
        return {"success": False, "error": "Empty or too small audio payload"}

    # Convert to WAV via ffmpeg (handles WebM, OGG, WAV, etc.)
    wav_data = _convert_to_wav(audio_data)
    if wav_data is None:
        # If conversion fails, try raw WAV as fallback
        wav_data = audio_data

    # Validate WAV header
    try:
        with wave.open(io.BytesIO(wav_data)) as wf:
            if wf.getnframes() == 0:
                return {"success": False, "error": "Empty audio — no frames detected after conversion"}
    except wave.Error as e:
        return {"success": False, "error": f"Invalid audio format after conversion: {e}"}
    except Exception as e:
        return {"success": False, "error": f"Cannot read converted audio: {e}"}

    recognizer = sr.Recognizer()

    try:
        with sr.AudioFile(io.BytesIO(wav_data)) as source:
            audio = recognizer.record(source)
    except Exception as e:
        logger.warning("ASR: speech_recognition could not open audio: %s", e)
        return {"success": False, "error": f"Audio format not supported by recognizer: {e}"}

    # Run es-AR and en-US in parallel
    with ThreadPoolExecutor(max_workers=2) as pool:
        future_es = pool.submit(_recognize, recognizer, audio, "es-AR")
        future_en = pool.submit(_recognize, recognizer, audio, "en-US")
        transcript_es = future_es.result()
        transcript_en = future_en.result()

    primary = transcript_es if transcript_es else transcript_en

    if not primary:
        return {"success": False, "error": "Google Speech API did not return a transcript in either language"}

    return {
        "success": True,
        "transcript": primary,
        "transcript_es": transcript_es or "",
        "transcript_en": transcript_en or "",
    }


def _convert_to_wav(audio_data: bytes) -> bytes | None:
    """Convert audio bytes to WAV PCM 16-bit mono via ffmpeg."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".in", delete=False) as fin:
            fin.write(audio_data)
            in_path = fin.name

        out_path = in_path + ".wav"

        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", in_path, "-ac", "1", "-ar", "16000",
                 "-sample_fmt", "s16", out_path],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning("ffmpeg conversion failed (rc=%d): %s",
                               result.returncode, result.stderr[:200])
                return None

            with open(out_path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("ffmpeg not found on system")
            return None
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg conversion timed out")
            return None
        except Exception as e:
            logger.warning("ffmpeg error: %s", e)
            return None
        finally:
            try:
                os.unlink(in_path)
            except OSError:
                pass
            try:
                os.unlink(out_path)
            except OSError:
                pass

    except Exception as e:
        logger.warning("Failed to create temp file for ffmpeg: %s", e)
        return None


def _recognize(recognizer: sr.Recognizer, audio: sr.AudioData, language: str) -> str:
    """Run Google Speech recognition for one language."""
    try:
        result = recognizer.recognize_google(audio, language=language)
        logger.debug("ASR ok [%s]: %s", language, result[:80])
        return result
    except sr.UnknownValueError:
        logger.debug("ASR: Google could not understand [%s]", language)
        return ""
    except sr.RequestError as e:
        logger.debug("ASR: Google request failed [%s]: %s", language, e)
        return ""
    except Exception as e:
        logger.debug("ASR: unexpected error [%s]: %s", language, e)
        return ""
