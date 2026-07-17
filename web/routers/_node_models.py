"""Pydantic models shared by node routers.

``NodeRolePayload`` was removed — it was dead code from inception (commit
``feac04d``): ``/promote`` and ``/demote`` never accepted a body payload.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class NodeHeartbeatPayload(BaseModel):
    node_id: str = Field(default="", max_length=128)
    role: str = Field(default="secondary", max_length=32)
    base_url: str = Field(default="", max_length=2048)
    metadata: dict = Field(default_factory=dict)


class NodeEventPayload(BaseModel):
    type: str = Field(default="unknown", max_length=128)
    data: dict | list | str | int | float | bool | None = None
    source: dict = Field(default_factory=dict)


class NodeMemoryWritePayload(BaseModel):
    key: str = Field(default="", max_length=512)
    value: str = Field(default="", max_length=262144)
    source: dict = Field(default_factory=dict)


class NodeEmbeddingJobItem(BaseModel):
    source: str = Field(default="session", max_length=64)
    source_key: str = Field(default="", max_length=512)
    item_idx: int = Field(default=0)
    text: str = Field(default="", max_length=32768)
    content_hash: str = Field(default="", max_length=128)


class NodeEmbeddingJobPayload(BaseModel):
    items: list[NodeEmbeddingJobItem] = Field(default_factory=list, max_length=64)
    source: dict = Field(default_factory=dict)
    dry_run: bool = Field(default=False)
