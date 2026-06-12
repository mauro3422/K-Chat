import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

from src.api.chat import get_default_model
from src.api.session import get_sessions
from src.llm.model_state import PRIORITY, FALLBACK_MODEL, get_verified_models_safe
from web.services.message_renderer import render_session_messages

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
templates.env.auto_reload = True

_NOCACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate"}


def get_available_model_ids() -> list[str]:
    verified = get_verified_models_safe()
    free_ids = verified or []
    models = list(PRIORITY)
    for fid in free_ids:
        if fid not in models:
            models.append(fid)
    if (verified is None or not free_ids) and FALLBACK_MODEL not in models:
        models.append(FALLBACK_MODEL)
    return models


@router.get("/favicon.ico")
def favicon() -> FileResponse:
    return FileResponse(Path(__file__).parent.parent / "static" / "logo.png")


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    models = get_available_model_ids()
    resp = templates.TemplateResponse(request, "chat.html", {
        "session_id": str(uuid.uuid4()),
        "model": get_default_model(),
        "models": models
    })
    resp.headers.update(_NOCACHE_HEADERS)
    return resp


@router.get("/sessions/{session_id}", response_class=HTMLResponse)
def session_page(request: Request, session_id: str) -> HTMLResponse:
    models = get_available_model_ids()
    resp = templates.TemplateResponse(request, "chat.html", {
        "session_id": session_id,
        "model": get_default_model(),
        "models": models
    })
    resp.headers.update(_NOCACHE_HEADERS)
    return resp


@router.get("/sidebar", response_class=HTMLResponse)
def sidebar(request: Request) -> HTMLResponse:
    raw = get_sessions(50)
    current = request.query_params.get("current", "")
    sessions = []
    for s in raw:
        sid, first, last, count, user_count, name = s
        sessions.append({
            "sid": sid,
            "first_str": str(first),
            "last_str": str(last),
            "count": count,
            "user_count": user_count,
            "name": name,
        })
    return templates.TemplateResponse(request, "sidebar.html", {"sessions": sessions, "current": current})


@router.get("/sessions/{session_id}/messages", response_class=HTMLResponse)
def session_messages(session_id: str) -> HTMLResponse:
    return HTMLResponse(render_session_messages(session_id))
