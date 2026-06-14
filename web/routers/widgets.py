import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api import sanitize_widget_id, get_repos

logger = logging.getLogger(__name__)
router = APIRouter()


class WidgetStatePayload(BaseModel):
    state: str = "{}"
    codeEntries: dict[str, str] | None = None


class SaveWidgetPayload(BaseModel):
    code: str
    description: str = ""


@router.post("/sessions/{session_id}/widgets/{widget_id}/state")
async def set_widget_state(session_id: str, widget_id: str, payload: WidgetStatePayload) -> dict[str, str]:
    repos = get_repos()
    await repos.sessions.require_session(session_id)
    widget_id = sanitize_widget_id(widget_id)
    await repos.widget_states.save_state(session_id, widget_id, payload.state)
    if payload.codeEntries:
        for code_key, code_value in payload.codeEntries.items():
            await repos.widget_states.save_state(session_id, code_key, code_value)
    return {"status": "ok"}


@router.get("/sessions/{session_id}/widgets/states")
async def get_all_widget_states(session_id: str) -> dict[str, str]:
    repos = get_repos()
    await repos.sessions.require_session(session_id)
    return await repos.widget_states.get_states(session_id)


@router.get("/sessions/{session_id}/widgets/{widget_id}/code")
async def get_widget_code(session_id: str, widget_id: str) -> Any:
    repos = get_repos()
    await repos.sessions.require_session(session_id)
    widget = await repos.saved_widgets.get(widget_id)
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found.")
    return widget


@router.get("/sessions/{session_id}/widgets/{widget_id}/versions")
async def get_widget_versions(session_id: str, widget_id: str) -> dict[str, Any]:
    repos = get_repos()
    await repos.sessions.require_session(session_id)
    versions = await repos.saved_widgets.get_versions(widget_id)
    return {"versions": versions}


@router.get("/sessions/{session_id}/widgets/{widget_id}/versions/{version}/code")
async def get_widget_version_code(session_id: str, widget_id: str, version: int) -> Any:
    repos = get_repos()
    await repos.sessions.require_session(session_id)
    widget = await repos.saved_widgets.get_by_version(widget_id, version)
    if not widget:
        raise HTTPException(status_code=404, detail="Widget version not found.")
    return widget


@router.post("/sessions/{session_id}/widgets/{widget_id}/save")
async def save_widget(session_id: str, widget_id: str, payload: SaveWidgetPayload) -> dict[str, Any]:
    repos = get_repos()
    await repos.sessions.require_session(session_id)
    if not payload.code.strip():
        raise HTTPException(status_code=400, detail="Code cannot be empty.")

    clean_id = sanitize_widget_id(widget_id)
    if not clean_id:
        raise HTTPException(status_code=400, detail="Invalid widget identifier.")

    try:
        res = await repos.saved_widgets.save(session_id, clean_id, payload.code, payload.description)
        return {"status": "ok", "widget_id": clean_id, "version": res["version"]}
    except Exception as e:
        logger.error("Error saving widget: %s", e)
        raise HTTPException(status_code=500, detail="Internal error saving widget.")
