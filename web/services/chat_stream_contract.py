"""Contracts for building backend chat stream generators."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable, Generator
from typing import Any

from web.services.loop_detector import LoopDetector
from web.services.protocols import (
    MessagePersisterProtocol,
    SessionArtifactCoordinatorProtocol,
)
from web.services.stream_retry_handler import StreamRetryHandler


@dataclass(slots=True)
class StreamGeneratorDeps:
    """Optional dependency bundle for chat stream generation."""

    chat_stream_fn: Callable[..., Generator[Any, None, None]] | None = None
    loop_detector: LoopDetector | None = None
    retry_handler: StreamRetryHandler | None = None
    save_fn: MessagePersisterProtocol | None = None
    rename_fn: Callable | None = None
    session_artifact_coordinator: SessionArtifactCoordinatorProtocol | None = None
    original_message: str = ""
    retry_error_type: str = ""
    retry_error_message: str = ""
    retry_count: int = 0
    initial_phases: list[dict[str, Any]] = field(default_factory=list)
    clock: Callable[[], float] | None = None
