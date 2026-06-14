import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

from src.llm.model_state import PRIORITY, FALLBACK_MODEL, get_verified_models_safe
from src.memory.repos import get_repos
from web.services.message_renderer import render_session_messages
from web.services.message_renderer_contract import MessageRenderDeps
from web.services.model_catalog import format_model_label, get_model_metadata
from src.config_loader import DEFAULT_CONFIG

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
templates.env.auto_reload = True

_NOCACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate"}

# ── Model tier definitions ────────────────────────────────────────────
GO_PREMIUM = {"glm-5.1", "kimi-k2.7-code", "qwen3.7-max"}
GO_STANDARD = {"deepseek-v4-pro", "deepseek-v4-flash", "mimo-v2.5-pro", "mimo-v2.5"}
GO_ECONOMY = {"minimax-m3", "minimax-m2.7", "qwen3.7-plus", "qwen3.6-plus", "qwen3.5-plus"}
ALL_GO = GO_PREMIUM | GO_STANDARD | GO_ECONOMY
FREE_SUFFIXES = ("-free", "-mini", "-nano")


def _get_model_tier(model_id: str) -> str:
    """Classify a model ID into a tier group."""
    if model_id in GO_PREMIUM:
        return "go_premium"
    if model_id in GO_STANDARD:
        return "go_standard"
    if model_id in GO_ECONOMY:
        return "go_economy"
    if model_id.endswith(FREE_SUFFIXES) or model_id in {"mimo-v2.5-free", "nemotron-3-ultra-free", "north-mini-code-free"}:
        return "free_ratelimited"
    return "zen"


def get_available_model_ids() -> list[str]:
    verified = get_verified_models_safe()
    all_ids = verified or []
    models = list(PRIORITY)
    for fid in all_ids:
        if fid not in models:
            models.append(fid)
    if (not verified or not all_ids) and FALLBACK_MODEL not in models:
        models.append(FALLBACK_MODEL)
    if DEFAULT_CONFIG.llm_mode == "go":
        seen = set(models)
        for m in ALL_GO:
            if m not in seen and (not all_ids or m in all_ids):
                models.append(m)
                seen.add(m)
        if not all_ids:
            for m in ALL_GO:
                if m not in seen:
                    models.append(m)
                    seen.add(m)
    return models


def get_available_models() -> list[dict[str, str]]:
    """Return models grouped by tier for the UI selector."""
    grouped = {"go_premium": [], "go_standard": [], "go_economy": [], "free_ratelimited": [], "zen": []}
    for model_id in get_available_model_ids():
        tier = _get_model_tier(model_id)
        label = format_model_label(model_id)
        meta = get_model_metadata(model_id)
        # Add visual indicators
        if tier == "free_ratelimited":
            label = "⚠️ " + label
        elif tier == "go_premium":
            label = "🚀 " + label
        elif tier == "go_standard":
            label = "⚡ " + label
        elif tier == "go_economy":
            label = "💰 " + label
        grouped[tier].append({"id": model_id, "label": label, "tier": tier})
    return grouped


@router.get("/favicon.ico")
def favicon() -> FileResponse:
    return FileResponse(Path(__file__).parent.parent / "static" / "logo.png")


@router.get("/", response_class=HTMLResponse)
def home(request: Request, new: bool = False) -> HTMLResponse:
    # ?new=1 forces a brand new session
    if new:
        session_id = str(uuid.uuid4())
    else:
        session_id = request.cookies.get("kchat_session_id")
        if not session_id:
            session_id = str(uuid.uuid4())
    resp = templates.TemplateResponse(request, "chat.html", {
        "session_id": session_id,
        "model": FALLBACK_MODEL,
        "models": get_available_models(),
    })
    resp.headers.update(_NOCACHE_HEADERS)
    # Always refresh the cookie so "new" actually persists
    resp.set_cookie("kchat_session_id", session_id, max_age=86400 * 30)
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
async def sidebar(request: Request) -> HTMLResponse:
    repos = get_repos()
    raw = await repos.sessions.get_all(50)
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
async def session_messages(session_id: str) -> dict:
    return await render_session_messages(session_id, deps=MessageRenderDeps(repos=get_repos()))
