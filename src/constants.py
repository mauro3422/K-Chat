"""Shared policy constants that should not live inside a feature package."""

TOOL_OUTPUT_CHUNK_SIZE = 12


def max_tool_turns(config=None):
    from src.config_loader import DEFAULT_CONFIG
    cfg = config or DEFAULT_CONFIG
    return cfg.max_tool_turns


# Backward compat — module-level constant
MAX_TOOL_TURNS = max_tool_turns()
