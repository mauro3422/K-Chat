"""Shared contracts for tools layer.

``HistoryMessage`` is re-exported from ``src._types`` (neutral location)
so tools layer never imports from ``src.memory`` directly.
"""

from src._types import HistoryMessage  # noqa: F401

__all__ = ["HistoryMessage"]
