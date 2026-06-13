"""ASR router — receive audio via POST and return transcribed text.

Uses Google Speech API via speech_recognition library.
Adapted from DuckSugar (transcribe_server.py).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from web.services.asr_service import transcribe_audio

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/api/asr/transcribe")
async def asr_transcribe(request: Request):
    """Receive a WAV audio file in the request body and return transcribed text.

    Expects:
        Content-Type: audio/wav (or application/octet-stream)
        Body: raw WAV audio bytes

    Returns:
        JSON with success, transcript, and optional error.
    """
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_AUDIO_SIZE:
        return JSONResponse(
            {"success": False, "error": f"Audio too large ({content_length} bytes, max {MAX_AUDIO_SIZE})"},
            status_code=413,
        )

    audio_data = await request.body()

    if not audio_data or len(audio_data) < 44:  # WAV header is 44 bytes minimum
        return JSONResponse(
            {"success": False, "error": "Empty or invalid audio payload"},
            status_code=400,
        )

    logger.info("ASR: received %d bytes of audio", len(audio_data))

    try:
        result = transcribe_audio(audio_data)
    except Exception as e:
        logger.exception("ASR: internal error during transcription")
        return JSONResponse(
            {"success": False, "error": f"Transcription failed: {e}"},
            status_code=500,
        )

    if result.get("success"):
        logger.info("ASR: transcribed %d chars", len(result.get("transcript", "")))
        return JSONResponse(result)
    else:
        logger.warning("ASR: transcription failed: %s", result.get("error"))
        return JSONResponse(result, status_code=422)
