import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api import save_widget_state, db_save_widget, db_get_widget, db_get_widget_versions, db_get_widget_by_version, sanitize_widget_id

logger = logging.getLogger(__name__)
router = APIRouter()


class WidgetStatePayload(BaseModel):
    state: str = "{}"


class SaveWidgetPayload(BaseModel):
    code: str
    description: str = ""


@router.post("/sessions/{session_id}/widgets/{widget_id}/state")
def set_widget_state(session_id: str, widget_id: str, payload: WidgetStatePayload) -> dict[str, str]:
    widget_id = sanitize_widget_id(widget_id)
    save_widget_state(session_id, widget_id, payload.state)
    return {"status": "ok"}


@router.get("/sessions/{session_id}/widgets/{widget_id}/code")
def get_widget_code(session_id: str, widget_id: str) -> Any:
    widget = db_get_widget(widget_id)
    if not widget:
        raise HTTPException(status_code=404, detail="Widget no encontrado.")
    return widget


@router.get("/sessions/{session_id}/widgets/{widget_id}/versions")
def get_widget_versions(session_id: str, widget_id: str) -> dict[str, Any]:
    versions = db_get_widget_versions(widget_id)
    return {"versions": versions}


@router.get("/sessions/{session_id}/widgets/{widget_id}/versions/{version}/code")
def get_widget_version_code(session_id: str, widget_id: str, version: int) -> Any:
    widget = db_get_widget_by_version(widget_id, version)
    if not widget:
        raise HTTPException(status_code=404, detail="Versión del widget no encontrada.")
    return widget


@router.post("/sessions/{session_id}/widgets/{widget_id}/save")
def save_widget(session_id: str, widget_id: str, payload: SaveWidgetPayload) -> dict[str, Any]:
    if not payload.code.strip():
        raise HTTPException(status_code=400, detail="El código no puede estar vacío.")
    
    clean_id = sanitize_widget_id(widget_id)
    if not clean_id:
        raise HTTPException(status_code=400, detail="Identificador de widget inválido.")

    try:
        res = db_save_widget(session_id, clean_id, payload.code, payload.description)
        return {"status": "ok", "widget_id": clean_id, "version": res["version"]}
    except Exception as e:
        logger.error("Error saving widget: %s", e)
        raise HTTPException(status_code=500, detail="Internal error saving widget.")

