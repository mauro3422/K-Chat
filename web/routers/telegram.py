"""Telegram observability endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from web.services.telegram_reflection import get_telegram_reflection_state

router = APIRouter(prefix="/api/telegram")


@router.get("/status")
async def telegram_status(request: Request) -> JSONResponse:
    state = getattr(request.app.state, "telegram_reflection_state", None) or get_telegram_reflection_state()
    payload = state.snapshot()
    payload["ok"] = True
    return JSONResponse(payload)
