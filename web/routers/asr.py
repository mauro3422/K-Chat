"""ASR router — receive audio via POST and return transcribed text.

Uses Google Speech API via speech_recognition library.
Adapted from DuckSugar (transcribe_server.py).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from src.api import get_repos
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
    if content_length:
        try:
            if int(content_length) > MAX_AUDIO_SIZE:
                return JSONResponse(
                    {"success": False, "error": f"Audio too large ({content_length} bytes, max {MAX_AUDIO_SIZE})"},
                    status_code=413,
                )
        except (ValueError, TypeError):
            return JSONResponse(
                {"success": False, "error": f"Invalid Content-Length header: {content_length}"},
                status_code=400,
            )

    audio_data, content_type = await _read_audio_payload(request)
    session_id = request.query_params.get("session_id")

    if not audio_data or len(audio_data) < 44:  # WAV header is 44 bytes minimum
        return JSONResponse(
            {"detail": "Empty or invalid audio payload"},
            status_code=400,
        )

    logger.info("ASR: received %d bytes of audio", len(audio_data))

    try:
        result = _transcribe_segment(audio_data, content_type=content_type)
    except Exception as e:
        logger.exception("ASR: internal error during transcription")
        return JSONResponse(
            {"detail": "Transcription failed"},
            status_code=500,
        )

    if result.get("success"):
        logger.info("ASR: transcribed %d chars", len(result.get("transcript", "")))
        await _append_telemetry(
            session_id,
            {
                "transport": "http",
                "kind": "segment",
                "bytes": len(audio_data),
                "content_type": content_type or "",
                "success": True,
                "transcript": result.get("transcript", ""),
            },
        )
        return JSONResponse(result)
    else:
        logger.warning("ASR: transcription failed: %s", result.get("error"))
        await _append_telemetry(
            session_id,
            {
                "transport": "http",
                "kind": "segment",
                "bytes": len(audio_data),
                "content_type": content_type or "",
                "success": False,
                "error": result.get("error", ""),
            },
        )
        return JSONResponse(result, status_code=422)


@router.websocket("/api/asr/stream")
async def asr_stream(websocket: WebSocket):
    await websocket.accept()
    session_id = websocket.query_params.get("session_id")
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            text = message.get("text")
            if text:
                if text.strip().lower() == "close":
                    break
                continue

            audio_data = message.get("bytes")
            if not audio_data:
                continue

            if len(audio_data) > MAX_AUDIO_SIZE:
                await _append_telemetry(
                    session_id,
                    {
                        "transport": "ws",
                        "kind": "segment",
                        "bytes": len(audio_data),
                        "content_type": "audio/wav",
                        "success": False,
                        "error": f"Audio too large ({len(audio_data)} bytes, max {MAX_AUDIO_SIZE})",
                    },
                )
                await websocket.send_json({
                    "type": "transcript",
                    "success": False,
                    "error": f"Audio too large ({len(audio_data)} bytes, max {MAX_AUDIO_SIZE})",
                })
                continue

            try:
                result = _transcribe_segment(audio_data, content_type="audio/wav")
            except Exception as e:
                logger.exception("ASR websocket: transcription failed")
                await _append_telemetry(
                    session_id,
                    {
                        "transport": "ws",
                        "kind": "segment",
                        "bytes": len(audio_data),
                        "content_type": "audio/wav",
                        "success": False,
                        "error": str(e),
                    },
                )
                await websocket.send_json({
                    "type": "transcript",
                    "success": False,
                    "error": "Transcription failed",
                })
                continue

            await _append_telemetry(
                session_id,
                {
                    "transport": "ws",
                    "kind": "segment",
                    "bytes": len(audio_data),
                    "content_type": "audio/wav",
                    "success": bool(result.get("success")),
                    "transcript": result.get("transcript", ""),
                    "error": result.get("error", ""),
                },
            )
            await websocket.send_json({"type": "transcript", **result})
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


async def _read_audio_payload(request: Request) -> tuple[bytes, str | None]:
    content_type = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in content_type:
        form = await request.form()
        for value in form.values():
            read = getattr(value, "read", None)
            if callable(read):
                return await value.read(), getattr(value, "content_type", None)
        raise HTTPException(status_code=400, detail="Missing audio file in multipart payload")
    return await request.body(), request.headers.get("content-type")


def _transcribe_segment(audio_data: bytes, content_type: str | None = None):
    return transcribe_audio(audio_data, content_type=content_type)


async def _append_telemetry(session_id: str | None, event: dict) -> None:
    if not session_id:
        return
    try:
        repos = get_repos()
        await repos.debug.append_asr_telemetry(session_id, event)
    except Exception:
        logger.exception("ASR telemetry append failed for %s", session_id)
