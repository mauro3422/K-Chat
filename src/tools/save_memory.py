import os
import logging
import threading
from src.context import CONTEXT_DIR

logger = logging.getLogger(__name__)

_save_lock = threading.Lock()

DEFINITION = {
    "type": "function",
    "function": {
        "name": "save_memory",
        "description": "Persiste datos e información clave del usuario o sistema en MEMORY.md para recordarlos en futuras sesiones.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "La categoría o clave de la información (ej. 'Nombre', 'Preferencia', 'Tecnología', 'Proyecto')"
                },
                "value": {
                    "type": "string",
                    "description": "El valor o detalle a guardar. Si se pasa vacío, se elimina esta clave de la memoria."
                }
            },
            "required": ["key", "value"]
        }
    }
}

_HEADER_TEMPLATE = [
    "# MEMORY.md\n",
    "\n",
    "User: \n",
    "System: \n",
    "\n",
]


def _ensure_header(header_lines: list) -> list:
    """Garantiza que header_lines contenga # MEMORY.md, User:, System:."""
    has_title = any(l.strip().startswith("# MEMORY.md") for l in header_lines)
    has_user = any(l.strip().startswith("User:") for l in header_lines)
    has_system = any(l.strip().startswith("System:") for l in header_lines)

    if has_title and has_user and has_system:
        return header_lines

    logger.warning("MEMORY.md corrupto o sin header — reparando estructura")
    out = list(_HEADER_TEMPLATE)
    for l in header_lines:
        s = l.strip()
        if s and not s.startswith("# MEMORY.md") and not s.startswith("User:") and not s.startswith("System:"):
            out.append(l)
    return out


def run(key: str, value: str, _session_id: str = None) -> str:
    filepath = os.path.join(CONTEXT_DIR, "MEMORY.md")

    with _save_lock:
        header_lines = []
        memories = {}

        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception as e:
                return f"[ERROR]: No se pudo leer MEMORY.md: {e}"
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

        key_clean = key.strip()
        value_clean = value.strip()

        if not key_clean:
            return "[ERROR]: La clave ('key') no puede estar vacía."

        if value_clean:
            memories[key_clean] = value_clean
            action_msg = f"guardada la clave '{key_clean}' con el valor '{value_clean}'"
        else:
            if key_clean in memories:
                del memories[key_clean]
                action_msg = f"eliminada la clave '{key_clean}'"
            else:
                action_msg = f"la clave '{key_clean}' no existía en memoria"

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
        except Exception as e:
            return f"[ERROR]: No se pudo escribir en MEMORY.md: {e}"

    return f"Éxito: Se ha {action_msg} en MEMORY.md."
