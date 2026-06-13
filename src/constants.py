"""Shared policy constants that should not live inside a feature package."""

from src.config_loader import DEFAULT_CONFIG

MAX_TOOL_TURNS = DEFAULT_CONFIG.max_tool_turns
TOOL_OUTPUT_CHUNK_SIZE = 12
