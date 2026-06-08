import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

from src.core import get_default_model
from src.memory import get_sessions
from web.ui_utils import _match_tools_to_msgs, _render_msg_with_phases
from src.memory import get_session_messages, get_tool_history, get_widget_states
import json
import html

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
templates.env.cache = None

_NOCACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate"}


def get_available_model_ids() -> list:
    from src.llm import get_verified_models, PRIORITY
    try:
        free_ids = get_verified_models()
    except Exception:
        free_ids = ["deepseek-v4-flash-free"]
    
    models = list(PRIORITY)
    for fid in free_ids:
        if fid not in models:
            models.append(fid)
    return models


@router.get("/favicon.ico")
async def favicon():
    return FileResponse(Path(__file__).parent.parent / "static" / "logo.png")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    models = get_available_model_ids()
    resp = templates.TemplateResponse("chat.html", {
        "request": request,
        "session_id": str(uuid.uuid4()),
        "model": get_default_model(),
        "models": models
    })
    resp.headers.update(_NOCACHE_HEADERS)
    return resp


@router.get("/sessions/{session_id}", response_class=HTMLResponse)
async def session_page(request: Request, session_id: str):
    models = get_available_model_ids()
    resp = templates.TemplateResponse("chat.html", {
        "request": request,
        "session_id": session_id,
        "model": get_default_model(),
        "models": models
    })
    resp.headers.update(_NOCACHE_HEADERS)
    return resp


@router.get("/sidebar", response_class=HTMLResponse)
async def sidebar(request: Request):
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
    return templates.TemplateResponse("sidebar.html", {"request": request, "sessions": sessions, "current": current})


@router.get("/sessions/{session_id}/messages", response_class=HTMLResponse)
async def session_messages(session_id: str):
    msgs = get_session_messages(session_id)
    all_tools = get_tool_history(session_id, 100)
    msg_tool_map = _match_tools_to_msgs(msgs, all_tools)
    widget_states = get_widget_states(session_id)
    widget_states_json = json.dumps(widget_states, ensure_ascii=False)
    
    # Extraer widgets del contenido para registrarlos
    import re
    widget_registry = {}
    widget_index = 0
    widget_regex = re.compile(r'```html-widget\s*\n([\s\S]*?)\n```')
    
    parts = [
        f'<div id="messages-metadata" data-widget-states="{html.escape(widget_states_json)}" style="display:none;"></div>',
        '<div class="main-header">',
        '<span class="debug-toggle" onclick="toggleDebug()">&#128202; Debug</span>',
        '</div>',
        '<div id="messages">'
    ]
    for role, content, model, ts, reasoning, phases_str in msgs:
        matched = msg_tool_map.get(ts, []) if role == "assistant" else []
        phases = None
        if phases_str and phases_str != "[]":
            try:
                phases = json.loads(phases_str)
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Extraer widgets del contenido y registrarlos
        if role == "assistant" and content:
            for match in widget_regex.finditer(content):
                widget_id = f'widget-{widget_index}'
                widget_code = match.group(1).replace('?.', '.')
                widget_registry[widget_id] = widget_code
                widget_index += 1
        
        parts.append(_render_msg_with_phases(role, content, reasoning, matched, ts, phases))
    if not msgs:
        parts.append('<div class="empty-state">Envia un mensaje para empezar</div>')
    parts.append('</div>')

    parts.append(
        '<form id="chat-form">'
        '<input type="text" id="msg-input" placeholder="Escribe un mensaje..." autofocus>'
        '<button type="submit">Enviar</button>'
        '<span id="spinner" class="htmx-indicator"></span>'
        '</form>'
    )
    
    return HTMLResponse("\n".join(parts))


@router.get("/new-session")
async def new_session():
    return HTMLResponse(str(uuid.uuid4()))
