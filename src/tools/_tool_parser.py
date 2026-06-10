import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _parse_tool_call(tc: Any, tool_map: dict[str, Any]) -> tuple[str, dict[str, Any], str | None]:
    """Extracts (name, args, error) from a tool call object, unwrapping execute_action if needed."""
    name = tc.function.name
    raw_args = tc.function.arguments
    logger.debug("tool_runner RECV: name=%r id=%r arguments=%r", name, tc.id, raw_args)
    try:
        args = json.loads(raw_args) if raw_args else {}
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("tool_runner: invalid JSON in tool_call '%s' (%s): repr=%r error=%s", name, tc.id, raw_args, e)
        args = {}

    if name == "execute_action":
        inner_name = args.get("action_name")
        inner_args = args.get("arguments", {})
        if isinstance(inner_args, str):
            try:
                inner_args = json.loads(inner_args)
            except (json.JSONDecodeError, TypeError):
                pass
        name = inner_name or ""
        args = inner_args if isinstance(inner_args, dict) else {}

    error = None
    if not name or name.startswith("$") or name not in tool_map:
        error = f"[ERROR]: The tool '{name}' does not exist or is not valid."
    else:
        required = _get_required_params(name)
        missing = [p for p in required if p not in args or not str(args[p]).strip()]
        if missing:
            error = f"[ERROR in {name}]: Missing required parameters: {', '.join(missing)}. You must provide all required parameters."

    return name, args, error


def _get_required_params(tool_name: str) -> list[str]:
    import src.tools
    for t in src.tools.TOOLS:
        if t.get("function", {}).get("name") == tool_name:
            return t.get("function", {}).get("parameters", {}).get("required", [])
    return []
