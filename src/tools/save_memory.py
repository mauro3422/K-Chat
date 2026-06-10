import os
import logging
import threading
from typing import Any
from src.paths import CONTEXT_DIR

logger: logging.Logger = logging.getLogger(__name__)

_save_lock: threading.Lock = threading.Lock()

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "save_memory",
        "description": "Persists key user or system data to MEMORY.md so it can be recalled in future sessions.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The category or key of the information (e.g. 'Name', 'Preference', 'Technology', 'Project')."
                },
                "value": {
                    "type": "string",
                    "description": "The value or detail to save. If passed empty, this key is removed from memory."
                }
            },
            "required": ["key", "value"]
        }
    }
}

_HEADER_TEMPLATE: list[str] = [
    "# MEMORY.md\n",
    "\n",
    "User: \n",
    "System: \n",
    "\n",
]


def _ensure_header(header_lines: list[str]) -> list[str]:
    """Ensure header_lines contains # MEMORY.md, User:, System:."""
    has_title = any(line.strip().startswith("# MEMORY.md") for line in header_lines)
    has_user = any(line.strip().startswith("User:") for line in header_lines)
    has_system = any(line.strip().startswith("System:") for line in header_lines)

    if has_title and has_user and has_system:
        return header_lines

    logger.warning("MEMORY.md corrupt or missing header — repairing structure")
    out = list(_HEADER_TEMPLATE)
    for line in header_lines:
        s = line.strip()
        if s and not s.startswith("# MEMORY.md") and not s.startswith("User:") and not s.startswith("System:"):
            out.append(line)
    return out


def _apply_memory_operation(key: str, value: str, memories: dict[str, str]) -> str:
    key_clean = key.strip()
    value_clean = value.strip()

    if not key_clean:
        return "[ERROR] The key cannot be empty."

    if value_clean:
        memories[key_clean] = value_clean
        action_msg = f"saved key '{key_clean}' with value '{value_clean}'"
    else:
        if key_clean in memories:
            del memories[key_clean]
            action_msg = f"deleted key '{key_clean}'"
        else:
            action_msg = f"key '{key_clean}' did not exist in memory"
    return action_msg


def _write_memory_file(filepath: str, header_lines: list[str], memories: dict[str, str]) -> str | None:
    new_lines = list(header_lines)

    while new_lines and new_lines[-1].strip() == "":
        new_lines.pop()
    new_lines.append("\n")
    new_lines.append("## Memories\n")

    for k, v in sorted(memories.items()):
        new_lines.append(f"- **{k}**: {v}\n")

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception:
        logger.exception("Failed to write to MEMORY.md")
        return "[ERROR] Could not write to MEMORY.md."
    return None


def run(key: str, value: str, _session_id: str | None = None) -> str:
    filepath = os.path.join(CONTEXT_DIR, "MEMORY.md")

    with _save_lock:
        header_lines = []
        memories = {}

        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception:
                return "[ERROR] Could not read MEMORY.md."
        else:
            lines = list(_HEADER_TEMPLATE)

        in_memories_section = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- **") and "**:" in stripped:
                idx = stripped.find("**:")
                k = stripped[4:idx].strip()
                v = stripped[idx + 3 :].strip()
                memories[k] = v
            elif stripped.startswith("## Memories") or stripped.startswith("## Memoria"):
                in_memories_section = True
            elif not in_memories_section:
                header_lines.append(line)

        header_lines = _ensure_header(header_lines)

        action_msg = _apply_memory_operation(key, value, memories)
        if action_msg.startswith("[ERROR]"):
            return action_msg

        err = _write_memory_file(filepath, header_lines, memories)
        if err:
            return err

    return f"[OK] {action_msg} in MEMORY.md."
