import json as _json
import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from src.api.llm_client import (
    PRIORITY,
    FALLBACK_MODEL,
    get_verified_models_safe,
    get_model_registry,
    get_rate_limit_store,
)
from src.api.repos import get_repos
from web.services.diagnostics_snapshot import build_diagnostics_snapshot
from web.routers.sessions import _federated_session_entries
from web.services.message_renderer import render_session_messages
from web.services.message_renderer_contract import MessageRenderDeps
from web.services.protocols import MessageRendererProtocol
from web.services.model_catalog import format_model_label, format_model_json, get_model_metadata

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
templates.env.auto_reload = True

_NOCACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate"}
_STATIC_DIR = Path(__file__).parent.parent / "static"
_DIST_DIR = _STATIC_DIR / "dist" / "assets"


def _request_repos(request: Request):
    app = getattr(request, "app", None)
    state = getattr(app, "state", None) if app is not None else None
    repos = getattr(state, "repos", None) if state is not None else None
    return repos or get_repos()


def _request_web_base_url(request: Request | None = None) -> str:
    if request is None:
        return ""
    app = getattr(request, "app", None)
    state = getattr(app, "state", None) if app is not None else None
    cfg = getattr(state, "config", None) if state is not None else None
    web_base_url = str(getattr(cfg, "web_base_url", "") or "").rstrip("/") if cfg is not None else ""
    if web_base_url:
        return web_base_url
    try:
        return str(request.base_url).rstrip("/")
    except Exception:
        return ""


def _master_session_url(request: Request | None, session_id: str) -> str:
    base_url = _request_web_base_url(request)
    if not base_url:
        return f"/go/{session_id}"
    return f"{base_url}/go/{session_id}"


def _get_registry(request: Request | None = None):
    if request is not None:
        reg = getattr(request.app.state, "model_registry", None)
        if reg is not None:
            return reg
        raise RuntimeError("Model registry not initialized")
    return get_model_registry()


def _get_rate_store(request: Request | None = None):
    if request is not None:
        store = getattr(request.app.state, "rate_limit_store", None)
        if store is not None:
            return store
        raise RuntimeError("Rate limit store not initialized")
    return get_rate_limit_store()


# ── NO HARDCODED MODEL NAMES ──────────────────────────────────────────
# Model discovery is fully dynamic via ModelRegistry (src/llm/model_registry.py).
# Models come from the Go and Zen APIs, tiers are inferred heuristically.
# See _infer_tier() in model_registry.py for the naming heuristics.


def _get_model_tier(model_id: str, request: Request | None = None) -> str:
    """Classify a model into a tier using the dynamic ModelRegistry.

    No hardcoded model names — everything comes from the API.
    """
    reg = _get_registry(request)
    return reg.get_tier(model_id)


def _get_registry_go_models(request: Request | None = None) -> list[str]:
    """Get Go models from the dynamic registry (not hardcoded)."""
    reg = _get_registry(request)
    return reg.get_go_models()


def get_available_model_ids(request: Request | None = None) -> list[str]:
    reg = _get_registry(request)
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


def get_available_models(request: Request | None = None) -> dict[str, list[dict]]:
    """Return models grouped by tier for the UI selector.

    Fully dynamic — no hardcoded model names.
    Each entry includes JSON metadata for the frontend custom dropdown.
    """
    rl = _get_rate_store(request)
    grouped: dict[str, list[dict]] = {
        "go_premium": [], "go_standard": [], "go_economy": [],
        "free_ratelimited": [],
    }
    for model_id in get_available_model_ids(request=request):
        tier = _get_model_tier(model_id, request=request)
        if tier == "zen":
            continue
        meta = format_model_json(model_id)
        cooldown = rl.get_cooldown_remaining(model_id)
        if cooldown is not None:
            meta["cooldown"] = int(cooldown)
            meta["label"] = f'{meta.get("label", model_id)} · {int(cooldown)}s'
        grouped[tier].append(meta)
    return grouped


def resolve_frontend_entry(preferred_name: str = "app_mock.js", fallback_name: str = "app.js") -> str:
    """Return the best available frontend entrypoint.

    Uses the Vite-built bundle when present, otherwise falls back to the
    checked-in ESM source so the app remains usable without a build step.
    """
    bundled = _DIST_DIR / preferred_name
    if bundled.exists():
        return f"/static/dist/assets/{preferred_name}?v={bundled.stat().st_mtime_ns}"
    fallback = _STATIC_DIR / fallback_name
    version = fallback.stat().st_mtime_ns if fallback.exists() else 0
    return f"/static/{fallback_name}?v={version}"


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
    _models = get_available_models(request=request)
    resp = templates.TemplateResponse(request, "chat_ts.html", {
        "session_id": session_id,
        "model": FALLBACK_MODEL,
        "models": _models,
        "models_json": _json.dumps(_models),
        "master_session_base_url": _request_web_base_url(request),
        "master_session_url": _master_session_url(request, session_id),
        "frontend_entry": resolve_frontend_entry("app_mock.js", "app_mock.js"),
    })
    resp.headers.update(_NOCACHE_HEADERS)
    # Always refresh the cookie so "new" actually persists
    resp.set_cookie("kchat_session_id", session_id, max_age=86400 * 30)
    return resp


@router.get("/sessions/{session_id}", response_class=HTMLResponse)
async def session_page(request: Request, session_id: str) -> Response:
    target = await _resolve_session_entry(request, session_id)
    if target:
        source_mode = str(target.get("source_mode", "local") or "local")
        source_url = str(target.get("source_url", "") or "").rstrip("/")
        current_base = str(request.base_url).rstrip("/")
        if source_mode == "peer" and source_url and source_url != current_base:
            return RedirectResponse(url=f"{source_url}/sessions/{session_id}", status_code=307)
    _models2 = get_available_models(request=request)
    resp = templates.TemplateResponse(request, "chat_ts.html", {
        "session_id": session_id,
        "model": FALLBACK_MODEL,
        "models": _models2,
        "models_json": _json.dumps(_models2),
        "master_session_base_url": _request_web_base_url(request),
        "master_session_url": _master_session_url(request, session_id),
        "frontend_entry": resolve_frontend_entry("app_mock.js", "app_mock.js"),
    })
    resp.headers.update(_NOCACHE_HEADERS)
    return resp


@router.get("/sidebar", response_class=HTMLResponse)
async def sidebar(request: Request) -> HTMLResponse:
    raw_sessions = await _federated_session_entries(request, 50)
    current = request.query_params.get("current", "")
    sessions = []
    for s in raw_sessions:
        sessions.append({
            "sid": s.get("id", ""),
            "first_str": s.get("first_str", ""),
            "last_str": s.get("last_str", ""),
            "count": s.get("count", 0),
            "name": s.get("name", ""),
            "is_favorite": s.get("is_favorite", False),
            "node_id": s.get("node_id", ""),
            "node_role": s.get("node_role", ""),
            "node_platform": s.get("node_platform", ""),
        })
    resp = templates.TemplateResponse(request, "sidebar.html", {"sessions": sessions, "current": current})
    resp.headers.update(_NOCACHE_HEADERS)
    return resp


@router.get("/diagnostics", response_class=HTMLResponse)
async def diagnostics(request: Request) -> HTMLResponse:
    snapshot = await build_diagnostics_snapshot(request, key_pattern=request.query_params.get("key_pattern", ""))
    resp = templates.TemplateResponse(request, "diagnostics.html", {
        "snapshot": snapshot,
    })
    resp.headers.update(_NOCACHE_HEADERS)
    return resp


async def _resolve_session_entry(request: Request, session_id: str) -> dict | None:
    try:
        sessions = await _federated_session_entries(request, 200)
    except Exception:
        return None
    for session in sessions:
        if session.get("id") == session_id:
            return session
    return None


@router.get("/go/{session_id}", response_class=HTMLResponse)
async def go_session(request: Request, session_id: str) -> Response:
    target = await _resolve_session_entry(request, session_id)
    if target:
        source_mode = str(target.get("source_mode", "local") or "local")
        source_url = str(target.get("source_url", "") or "").rstrip("/")
        current_base = str(request.base_url).rstrip("/")
        if source_mode == "peer" and source_url and source_url != current_base:
            return RedirectResponse(url=f"{source_url}/go/{session_id}", status_code=307)
    _models3 = get_available_models(request=request)
    resp = templates.TemplateResponse(request, "chat_ts.html", {
        "session_id": session_id,
        "model": FALLBACK_MODEL,
        "models": _models3,
        "models_json": _json.dumps(_models3),
        "master_session_base_url": _request_web_base_url(request),
        "master_session_url": _master_session_url(request, session_id),
        "frontend_entry": resolve_frontend_entry("app_mock.js", "app_mock.js"),
    })
    resp.headers.update(_NOCACHE_HEADERS)
    return resp


@router.get("/sessions/{session_id}/messages")
async def session_messages(request: Request, session_id: str) -> dict:
    return await render_session_messages(session_id, deps=MessageRenderDeps(repos=_request_repos(request)))
