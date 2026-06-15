"""move_file: mueve o copia archivos y directorios.

Cubre las operaciones que antes requerían execute_command (mv, cp).
Sigue el patrón Lego: DEFINITION + run().
"""

import os
import shutil
import asyncio
from typing import Any

from src.tools._path_helpers import resolve_and_validate_path

logger: Any = __import__('logging').getLogger(__name__)

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "move_file",
        "description": (
            "Mueve, renombra o copia archivos y directorios. "
            "Reemplaza mv y cp. Operaciones: 'move' (mover/renombrar), 'copy' (copiar). "
            "El destino puede ser un directorio (preserva nombre) o una ruta completa."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["move", "copy"],
                    "description": "'move' = mover/renombrar, 'copy' = copiar",
                    "default": "move"
                },
                "source": {
                    "type": "string",
                    "description": "Ruta del archivo o directorio origen"
                },
                "dest": {
                    "type": "string",
                    "description": "Ruta de destino (archivo o directorio)"
                }
            },
            "required": ["source", "dest"]
        }
    }
}


def _sync_move_file(operation: str, source: str, dest: str) -> str:
    """Sync: ejecuta move/copy. Corre en to_thread."""
    src_resolved, err = resolve_and_validate_path(source)
    if err:
        return f"[ERROR] {err}"

    if not os.path.exists(src_resolved):
        return f"[ERROR] El origen '{source}' no existe."

    dest_resolved = os.path.expanduser(dest)
    if not os.path.isabs(dest_resolved):
        dest_resolved = os.path.abspath(dest_resolved)

    if os.path.isdir(dest_resolved):
        dest_resolved = os.path.join(dest_resolved, os.path.basename(src_resolved))

    dest_dir = os.path.dirname(dest_resolved)
    os.makedirs(dest_dir, exist_ok=True)

    try:
        if operation == "copy":
            if os.path.isfile(src_resolved):
                result = shutil.copy2(src_resolved, dest_resolved)
            elif os.path.isdir(src_resolved):
                result = shutil.copytree(src_resolved, dest_resolved, dirs_exist_ok=True)
            else:
                return f"[ERROR] Tipo de archivo no soportado: {source}"
            return f"[OK] Copiado: {source} -> {result}"
        else:
            result = shutil.move(src_resolved, dest_resolved)
            return f"[OK] Movido: {source} -> {result}"
    except shutil.Error as e:
        return f"[ERROR] Error de shutil: {e}"
    except PermissionError:
        return f"[ERROR] Permiso denegado"
    except OSError as e:
        return f"[ERROR] Error del sistema: {e}"
    except Exception as e:
        logger.exception("Error in move_file")
        return f"[ERROR] Error inesperado: {e}"


async def run(**kwargs: Any) -> str:
    operation = kwargs.get("operation", "move")
    source = kwargs.get("source", "").strip()
    dest = kwargs.get("dest", "").strip()

    if not source or not dest:
        return "[ERROR] Debes proporcionar source y dest."

    if operation not in ("move", "copy"):
        return "[ERROR] Operacion no valida. Usa 'move' o 'copy'."

    return await asyncio.to_thread(_sync_move_file, operation, source, dest)
