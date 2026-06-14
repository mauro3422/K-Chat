"""Contracts for assistant message persistence from web streams."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from src.api import MessageRecord


@dataclass(slots=True)
class MessagePersisterDeps:
    """Optional dependency bundle for assistant message persistence."""

    save_message_fn: Callable[[MessageRecord], None] | None = None
    save_debug_fn: Callable[[str, dict[str, Any]], None] | None = None
    message_record_cls: type[MessageRecord] | None = None
