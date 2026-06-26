"""LAN task bridge between Kairos and Codex."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from web.routers.debug import _trusted_lan_or_local
from web.services.codex_task_bridge import create_task, get_task, list_tasks, update_task


router = APIRouter(prefix="/api/codex")


class CodexTaskPayload(BaseModel):
    title: str = Field(default="")
    prompt: str = Field(default="")
    from_node: str = Field(default="")
    session_id: str = Field(default="")
    priority: str = Field(default="normal")


class CodexTaskUpdatePayload(BaseModel):
    status: str | None = Field(default=None)
    message: str = Field(default="")
    role: str = Field(default="codex")
    source: str = Field(default="codex")
    claimed_by: str = Field(default="")


@router.post("/tasks")
async def create_codex_task(payload: CodexTaskPayload, request: Request) -> JSONResponse:
    _trusted_lan_or_local(request)
    try:
        task = create_task(
            title=payload.title,
            prompt=payload.prompt,
            from_node=payload.from_node,
            session_id=payload.session_id,
            priority=payload.priority,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "task": task})


@router.get("/tasks")
async def list_codex_tasks(request: Request, status: str = "open", limit: int = 50) -> JSONResponse:
    _trusted_lan_or_local(request)
    tasks = list_tasks(status=status, limit=limit)
    return JSONResponse({"ok": True, "tasks": tasks, "count": len(tasks)})


@router.get("/tasks/{task_id}")
async def read_codex_task(task_id: str, request: Request) -> JSONResponse:
    _trusted_lan_or_local(request)
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return JSONResponse({"ok": True, "task": task})


@router.post("/tasks/{task_id}")
async def update_codex_task(task_id: str, payload: CodexTaskUpdatePayload, request: Request) -> JSONResponse:
    _trusted_lan_or_local(request)
    try:
        task = update_task(
            task_id,
            status=payload.status,
            message=payload.message,
            role=payload.role,
            source=payload.source,
            claimed_by=payload.claimed_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return JSONResponse({"ok": True, "task": task})
