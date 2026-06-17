import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

from src.api import PRIORITY, FALLBACK_MODEL, get_verified_models_safe
from src.api import get_model_registry, ensure_registry_refreshed
from src.api import get_rate_limit_store, get_repos
from web.services.message_renderer import render_session_messages
from web.services.message_renderer_contract import MessageRenderDeps
from web.services.protocols import MessageRendererProtocol
from web.services.model_catalog import format_model_label, get_model_metadata

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
templates.env.auto_reload = True

_NOCACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate"}
_STATIC_DIR = Path(__file__).parent.parent / "static"
_DIST_DIR = _STATIC_DIR / "dist" / "assets"


def _request_repos(request: Request):
    app = getattr(request, "app", None)
    state = getattr(app, "__dict__", {}).get("state") if app is not None else None
    repos = getattr(state, "repos", None) if state is not None else None
    return repos or get_repos()

# ── NO HARDCODED MODEL NAMES ──────────────────────────────────────────
# Model discovery is fully dynamic via ModelRegistry (src/llm/model_registry.py).
# Models come from the Go and Zen APIs, tiers are inferred heuristically.
# See _infer_tier() in model_registry.py for the naming heuristics.


def _get_model_tier(model_id: str) -> str:
    """Classify a model into a tier using the dynamic ModelRegistry.

    No hardcoded model names — everything comes from the API.
    """
    reg = get_model_registry()
    return reg.get_tier(model_id)


def _get_registry_go_models() -> list[str]:
    """Get Go models from the dynamic registry (not hardcoded)."""
    reg = get_model_registry()
    return reg.get_go_models()


def get_available_model_ids() -> list[str]:
    reg = get_model_registry()
    all_registry = reg.get_all_models()
    verified = get_verified_models_safe()
    seen: set[str] = set()

    # 1. Priority models first
    models = []
    for mid in list(PRIORITY):
        if mid not in seen and (mid in all_registry or mid in (verified or [])):
            models.append(mid)
            seen.add(mid)

    # 2. Verified models (includes Go + free from discovery)
    if verified:
        for mid in verified:
            if mid not in seen:
                models.append(mid)
                seen.add(mid)
    elif FALLBACK_MODEL not in seen:
        models.append(FALLBACK_MODEL)
        seen.add(FALLBACK_MODEL)

    # 3. All known registry models (Go API as source of truth)
    for mid in all_registry:
        if mid not in seen:
            models.append(mid)
            seen.add(mid)

    return models


def get_available_models() -> list[dict[str, str]]:
    """Return models grouped by tier for the UI selector.

    Fully dynamic — no hardcoded model names.
    Only shows Go (paid) and Free (rate-limited) models.
    Zen-only models (paid per-use, not OpenCode) are hidden.
    """
    rl = get_rate_limit_store()
    grouped: dict[str, list[dict[str, str]]] = {
        "go_premium": [], "go_standard": [], "go_economy": [],
        "free_ratelimited": [],
    }
    for model_id in get_available_model_ids():
        tier = _get_model_tier(model_id)
        if tier == "zen":
            continue  # Hide Zen-only models — paid per-use, not OpenCode
        label = format_model_label(model_id)
        # Add visual indicators
        if tier == "free_ratelimited":
            label = "⚠️ " + label
        elif tier == "go_premium":
            label = "🚀 " + label
        elif tier == "go_standard":
            label = "⚡ " + label
        elif tier == "go_economy":
            label = "💰 " + label

        # Rate limit cooldown badge
        cooldown = rl.get_cooldown_remaining(model_id)
        if cooldown is not None:
            label += f"  🔒 {int(cooldown)}s"

        grouped[tier].append({"id": model_id, "label": label, "tier": tier})
    return grouped


def resolve_frontend_entry(preferred_name: str = "app_mock.js", fallback_name: str = "app.js") -> str:
    """Return the best available frontend entrypoint.

    Uses the Vite-built bundle when present, otherwise falls back to the
    checked-in ESM source so the app remains usable without a build step.
    """
    bundled = _DIST_DIR / preferred_name
    if bundled.exists():
        return f"/static/dist/assets/{preferred_name}"
    return f"/static/{fallback_name}"


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
        "frontend_entry": resolve_frontend_entry("app_mock.js", "app_mock.js"),
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
        "frontend_entry": resolve_frontend_entry("app_mock.js", "app_mock.js"),
    })
    resp.headers.update(_NOCACHE_HEADERS)
    return resp


@router.get("/sidebar", response_class=HTMLResponse)
async def sidebar(request: Request) -> HTMLResponse:
    repos = _request_repos(request)
    raw = await repos.sessions.get_all(50)
    current = request.query_params.get("current", "")
    sessions = []
    for s in raw:
        sid, first, last, count, user_count, name = s[0], s[1], s[2], s[3], s[4], s[5]
        is_favorite = bool(s[7]) if len(s) > 7 else False
        sessions.append({
            "sid": sid,
            "first_str": str(first),
            "last_str": str(last),
            "count": count,
            "user_count": user_count,
            "name": name,
            "is_favorite": is_favorite,
        })
    resp = templates.TemplateResponse(request, "sidebar.html", {"sessions": sessions, "current": current})
    resp.headers.update(_NOCACHE_HEADERS)
    return resp


@router.get("/sessions/{session_id}/messages")
async def session_messages(session_id: str) -> dict:
    return await render_session_messages(session_id, deps=MessageRenderDeps(repos=get_repos()))
