"""read_multiple: lee múltiples archivos en una sola llamada.

Soporta rangos de líneas por archivo (ej: 'file.py:10-30').
Sigue el patrón Lego: DEFINITION + run().
"""
import asyncio
import os
import re
from typing import Any

from src.tools._path_helpers import resolve_and_validate_path
from src.utils.async_utils import run_in_thread

MAX_LINES_PER_FILE = 250
MAX_FILES = 10

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "read_multiple",
        "description": (
            "Lee MULTIPLES archivos en UNA sola llamada. "
            "Cada archivo puede incluir un rango de lineas (ej: 'src/core/tool_loop.py:1-50'). "
            "Acepta hasta 10 archivos por call, hasta 250 lineas cada uno (max 500 con max_lines). "
            "Ideal para leer modulos completos o comparar archivos relacionados."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Lista de rutas a leer. Cada ruta puede incluir rango: "
                        "'archivo.py' (completo), 'archivo.py:20-50' (lineas 20 a 50), "
                        "'archivo.py:30' (desde linea 30). Max 10 archivos."
                    )
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Max lineas por archivo (default: 250, max: 500)",
                    "default": 250
                }
            },
            "required": ["files"]
        }
    }
}


def _parse_file_spec(spec: str) -> tuple[str, int, int | None]:
    """Parsea 'archivo.py:10-30' → ('archivo.py', 10, 30)."""
    m = re.match(r'^(.+?)(?::(\d+)(?:-(\d+))?)?$', spec.strip())
    if not m:
        return spec.strip(), 1, None
    path = m.group(1).strip()
    start = int(m.group(2)) if m.group(2) else 1
    end = int(m.group(3)) if m.group(3) else None
    return path, start, end


def _read_single(path: str, start_line: int, end_line: int | None, max_lines: int = 250) -> str:
    """Lee un archivo con rango. Devuelve contenido formateado o error."""
    resolved, err = resolve_and_validate_path(path)
    if err:
        return f"[ERROR] {path}: {err}"

    if not os.path.exists(resolved):
        return f"[ERROR] '{path}' no existe."
    if os.path.isdir(resolved):
        return f"[ERROR] '{path}' es un directorio."

    try:
        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return f"[ERROR] '{path}': {e}"

    total = len(lines)
    start = max(1, start_line)
    if end_line is not None:
        end = min(total, max(start, end_line))
    else:
        end = min(total, start + max_lines - 1)

    shown = end - start + 1
    was_truncated = shown > max_lines
    if was_truncated:
        end = start + max_lines - 1

    out = [f"── {path} (lines {start}-{end}/{total}) ──\n"]
    for idx in range(start - 1, end):
        out.append(f"{idx + 1:4d}: {lines[idx]}")
    if was_truncated:
        out.append(f"[truncado, continua en linea {end + 1}]\n")

    return "".join(out)


async def run(**kwargs: Any) -> str:
    files: list = kwargs.get("files", [])
    max_lines = min(int(kwargs.get("max_lines", 250)), 500)
    if not files or not isinstance(files, list):
        return "[ERROR] Debes proporcionar una lista 'files' con las rutas a leer."

    if len(files) > MAX_FILES:
        return f"[ERROR] Maximo {MAX_FILES} archivos por llamada (pediste {len(files)})."
    # Ejecutar lecturas en paralelo con to_thread
    tasks = [run_in_thread(_read_single, *(_parse_file_spec(str(spec))), max_lines)
             for spec in files]
    results = await asyncio.gather(*tasks)

    return "\n\n".join(results)
