from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from web.routers.pages import FALLBACK_MODEL, get_available_models, resolve_frontend_entry

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

@router.get("/chat-ts", response_class=HTMLResponse)
def get_chat_ts(request: Request) -> HTMLResponse:
    resp = templates.TemplateResponse(request, "chat_ts.html", {
        "session_id": "sess-1",
        "model": FALLBACK_MODEL,
        "models": get_available_models(),
        "frontend_entry": resolve_frontend_entry("app_mock.js", "app_mock.js"),
    })
    resp.headers.update({"Cache-Control": "no-cache, no-store, must-revalidate"})
    return resp
