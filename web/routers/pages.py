import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

from src.llm.model_state import PRIORITY, FALLBACK_MODEL, get_verified_models_safe
from src.api.session import get_sessions
from src.memory.repos import get_repos
from web.services.message_renderer import render_session_messages
from web.services.message_renderer_contract import MessageRenderDeps
from web.services.model_catalog import format_model_label

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


def get_available_models() -> list[dict[str, str]]:
    return [{"id": model_id, "label": format_model_label(model_id)} for model_id in get_available_model_ids()]


@router.get("/favicon.ico")
def favicon() -> FileResponse:
    return FileResponse(Path(__file__).parent.parent / "static" / "logo.png")


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    resp = templates.TemplateResponse(request, "chat.html", {
        "session_id": str(uuid.uuid4()),
        "model": FALLBACK_MODEL,
        "models": get_available_models(),
    })
    resp.headers.update(_NOCACHE_HEADERS)
    return resp


@router.get("/sessions/{session_id}", response_class=HTMLResponse)
def session_page(request: Request, session_id: str) -> HTMLResponse:
    resp = templates.TemplateResponse(request, "chat.html", {
        "session_id": session_id,
        "model": FALLBACK_MODEL,
        "models": get_available_models(),
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


@router.get("/sessions/{session_id}/messages")
def session_messages(session_id: str) -> dict:
    return render_session_messages(session_id, deps=MessageRenderDeps(repos=get_repos()))
