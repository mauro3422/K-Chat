"""edit_file: edita líneas específicas de un archivo sin reescribirlo completo.

Útil para parchar funciones, corregir bugs, o modificar secciones
conocidas sin tener que re-enviar el archivo entero.
"""
import logging
import os
from typing import Any

from src.tools._path_helpers import resolve_and_validate_path

logger = logging.getLogger(__name__)

DEFINITION = {
    "type": "function",
    "function": {
        "name": "edit_file",
        "description": (
            "Edita lineas especificas de un archivo sin tener que reescribirlo completo. "
            "Usalo cuando sepas las lineas exactas a modificar (obtenidas con search_files o list_files). "
            "Soporta reemplazar rangos de lineas, insertar en una posicion, o eliminar lineas. "
            "Mucho mas eficiente que read_file + write_file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo a editar (absoluta o relativa)"
                },
                "start_line": {
                    "type": "integer",
                    "description": "Linea de inicio (1-indexed). Para reemplazar: desde esta linea. Para insertar: despues de esta linea (si no hay end_line). Para eliminar: desde esta linea (si new_content vacio)."
                },
                "end_line": {
                    "type": "integer",
                    "description": "Linea de fin (inclusive). Opcional: si solo start_line → inserta antes de esa linea. Si start_line + end_line → reemplaza ese rango. Si start_line + end_line + new_content vacio → borra ese rango."
                },
                "new_content": {
                    "type": "string",
                    "description": "El nuevo contenido a poner en lugar de las lineas. Si esta vacio y hay start/end_line, se borran esas lineas.",
                    "default": ""
                }
            },
            "required": ["path", "start_line"]
        }
    }
}

MAX_FILE_SIZE = 500 * 1024


def _lineno_safety(lines: list[str], n: int) -> int:
    """Asegura que el numero de linea este dentro del rango."""
    return max(1, min(n, len(lines)))


def run(**kwargs: Any) -> str:
    path = kwargs.get("path", "").strip()
    start_line = int(kwargs.get("start_line", 0))
    end_line = kwargs.get("end_line")
    if end_line is not None:
        end_line = int(end_line)
    new_content = kwargs.get("new_content", "")

    if not path:
        return "[ERROR] Proporciona una ruta de archivo."

    path, err = resolve_and_validate_path(path)
    if err:
        return err

    if not os.path.isfile(path):
        return f"[ERROR] El archivo '{path}' no existe."

    size = os.path.getsize(path)
    if size > MAX_FILE_SIZE:
        return f"[ERROR] Archivo demasiado grande ({size / 1024:.0f}KB)."

    # Leer archivo
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            original_lines = f.readlines()
    except Exception as e:
        return f"[ERROR] No se pudo leer: {e}"

    total_lines = len(original_lines)
    start = _lineno_safety(original_lines, start_line)

    # Determinar modo de operacion
    if end_line is not None:
        end = _lineno_safety(original_lines, end_line)
        # Validar orden
        if start > end:
            start, end = end, start
        if new_content:
            modo = "reemplazar"
            new_lines = new_content.splitlines(keepends=True)
            # Asegurar que termine en newline si el original si
            if new_lines and not new_lines[-1].endswith('\n') and original_lines and original_lines[-1].endswith('\n'):
                new_lines[-1] += '\n'
            result_lines = original_lines[:start-1] + new_lines + original_lines[end:]
        else:
            modo = "eliminar"
            result_lines = original_lines[:start-1] + original_lines[end:]
    elif new_content:
        # Solo start_line + content = insertar ANTES de la linea indicada
        modo = "insertar"
        new_lines = new_content.splitlines(keepends=True)
        if new_lines and not new_lines[-1].endswith('\n') and original_lines and original_lines[-1].endswith('\n'):
            new_lines[-1] += '\n'
        result_lines = original_lines[:start-1] + new_lines + original_lines[start-1:]
    else:
        return "[ERROR] Debes proporcionar new_content o end_line (o ambos)."

    # Escribir
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(result_lines)
    except Exception as e:
        return f"[ERROR] No se pudo escribir: {e}"

    diff = len(result_lines) - total_lines
    summary = f"✅ Editado: {path}\n"
    summary += f"   Modo: {modo} | Lineas: {start}"

    if end_line is not None:
        summary += f"-{end}"
    summary += f"\n   Lineas resultantes: {len(result_lines)} ({diff:+d})"

    # Validacion cross-language post-escritura
    from src.tools._validators import validate_file
    vresult = validate_file(path, ''.join(result_lines))
    if vresult['status'] == 'ok':
        summary += f"\n   ✅ {vresult['message']}"
    elif vresult['status'] == 'error':
        line_info = f" L{vresult['line']}" if vresult.get('line') else ""
        summary += f"\n   ⚠️ {vresult['message']}{line_info}"
    elif vresult['status'] == 'warning':
        summary += f"\n   ⚡ {vresult['message']}"

    return summary
