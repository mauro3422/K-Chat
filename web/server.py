import os, sys, uuid, json, html
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError

from src.core import chat_stream, build_system_prompt, get_default_model
from src.background_tasks import auto_rename_session
from web.ui_utils import _match_tools_to_msgs, _render_msg_with_phases
from src.memory import init_db, get_sessions, get_session_messages, get_tool_history
from src.memory import ensure_session, rename_session, delete_session, save_debug_info, get_debug_info, check_should_rename
from src.memory import save_message as db_save_message
from src.memory import save_widget_state, get_widget_states

app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.cache = None  # no cache
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return HTMLResponse("<h1>404 - No encontrado</h1><a href='/'>Volver</a>", status_code=404)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc):
    return JSONResponse({"error": "Datos inválidos", "detail": str(exc)}, status_code=422)


@app.exception_handler(Exception)
async def server_error(request: Request, exc):
    logger = logging.getLogger(__name__)
    logger.error("Error interno en %s: %s", request.url.path, exc)
    return HTMLResponse("<h1>500 - Error interno</h1><p>Ocurrió un error inesperado.</p>", status_code=500)

_NOCACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate"}

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

init_db()


def rebuild_history(session_id: str, model: str) -> list:
    rows = get_session_messages(session_id)
    history = [build_system_prompt(model)]
    for role, content, *_ in rows:
        if role != "system":
            history.append({"role": role, "content": content})
    return history


@app.get("/favicon.ico")
async def favicon():
    return FileResponse(Path(__file__).parent / "static" / "logo.png")


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


@app.get("/", response_class=HTMLResponse)
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


@app.get("/sessions/{session_id}", response_class=HTMLResponse)
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


@app.get("/sidebar", response_class=HTMLResponse)
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


@app.get("/sessions/{session_id}/messages", response_class=HTMLResponse)
async def session_messages(session_id: str):
    msgs = get_session_messages(session_id)
    all_tools = get_tool_history(session_id, 100)
    msg_tool_map = _match_tools_to_msgs(msgs, all_tools)
    widget_states = get_widget_states(session_id)
    widget_states_json = json.dumps(widget_states, ensure_ascii=False)
    parts = [
        f'<script>window.widgetStates = {widget_states_json};</script>',
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


@app.post("/chat/{session_id}")
async def chat(session_id: str, background_tasks: BackgroundTasks, message: str = Form(...), model: str = ""):
    if not session_id or not session_id.strip():
        raise HTTPException(400, "session_id inválido")
    if not message.strip():
        return ""
    if not model:
        model = get_default_model()

    ensure_session(session_id)
    try:
        history = rebuild_history(session_id, model)
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error("Error reconstruyendo historial para %s: %s", session_id, e)
        raise HTTPException(500, "Error al cargar historial")

    def generate():
        full_reasoning = ""
        full_content = ""
        debug_info = {}
        phases_output = []
        for tipo, token in chat_stream(message, history, model, session_id=session_id, tagged=True, debug=debug_info, phases_output=phases_output):
            if tipo == "reasoning":
                full_reasoning += token
            elif tipo == "content":
                full_content += token
            yield json.dumps({"t": tipo, "d": token}) + "\n"
        phases_json = json.dumps(phases_output, ensure_ascii=False)
        db_save_message(session_id, "user", message, model)
        pt = debug_info.get("prompt_tokens", 0)
        ct = debug_info.get("completion_tokens", 0)
        tt = debug_info.get("total_tokens", 0)
        db_save_message(
            session_id, "assistant", full_content, model,
            reasoning=full_reasoning, phases=phases_json,
            prompt_tokens=pt, completion_tokens=ct, total_tokens=tt
        )
        if not debug_info.get("phases"):
            debug_info["phases"] = phases_json
        save_debug_info(session_id, debug_info)
        background_tasks.add_task(auto_rename_session, session_id, message, model)

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@app.post("/sessions/{session_id}/rename")
async def rename(session_id: str, name: str = Form(...)):
    rename_session(session_id, name.strip() or session_id[:8])
    return HTMLResponse("OK")


@app.post("/sessions/{session_id}/delete")
async def delete(session_id: str):
    delete_session(session_id)
    return HTMLResponse("OK")


@app.get("/sessions/{session_id}/debug")
async def debug_info(session_id: str):
    d = get_debug_info(session_id)
    return JSONResponse(d)


@app.post("/sessions/{session_id}/widgets/{widget_id}/state")
async def set_widget_state(session_id: str, widget_id: str, payload: dict):
    state = payload.get("state", "{}")
    save_widget_state(session_id, widget_id, state)
    return {"status": "ok"}


@app.get("/new-session")
async def new_session():
    return HTMLResponse(str(uuid.uuid4()))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
