"""Pydantic models shared by node routers.

``NodeRolePayload`` was removed — it was dead code from inception (commit
``feac04d``): ``/promote`` and ``/demote`` never accepted a body payload.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class NodeHeartbeatPayload(BaseModel):
    node_id: str = Field(default="")
    role: str = Field(default="secondary")
    base_url: str = Field(default="")
    metadata: dict = Field(default_factory=dict)


class NodeEventPayload(BaseModel):
    type: str = Field(default="unknown")
    data: dict | list | str | int | float | bool | None = None
    source: dict = Field(default_factory=dict)


class NodeMemoryWritePayload(BaseModel):
    key: str = Field(default="")
    value: str = Field(default="")
    source: dict = Field(default_factory=dict)