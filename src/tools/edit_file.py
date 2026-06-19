import os
import logging
import shutil
from typing import Any

from src.tools._path_helpers import resolve_and_validate_path
from src.tools._preflight import preflight_check, create_backup, postflight_check
from src.utils.async_utils import run_awaitable_sync

logger = logging.getLogger(__name__)


class AwaitableText(str):
    def __new__(cls, value: str):
        return super().__new__(cls, value)

    def __await__(self):
        async def _wrap():
            return str(self)
        return _wrap().__await__()


def _run_impact_analysis(def_name: str, path: str) -> str | None:
    try:
        from src.tools.impact_analysis import run as impact_run
        return run_awaitable_sync(impact_run(name=def_name, path=path), label="impact analysis")
    except Exception:
        return None

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
                },
                "arch_check": {
                    "type": "boolean",
                    "description": "Si False, desactiva el post-hook de arch check + impact analysis (default: True)",
                    "default": True
                },
                "verbose": {
                    "type": "boolean",
                    "description": "Si True, muestra todos los post-hooks. Si False, solo muestra si hay problemas (default: True)",
                    "default": True
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


def _edit_file_sync(path: str, start_line: int, end_line: int | None, new_content: str) -> str:
    """Sync function: toda la lógica de edición con I/O. Corre en to_thread."""
    from src.tools._preflight import preflight_check, create_backup, postflight_check, rollback

    if not os.path.isfile(path):
        return f"[ERROR] El archivo '{path}' no existe."

    size = os.path.getsize(path)
    if size > MAX_FILE_SIZE:
        return f"[ERROR] Archivo demasiado grande ({size / 1024:.0f}KB."

    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            original_lines = f.readlines()
    except Exception as e:
        return f"[ERROR] No se pudo leer: {e}"

    preflight = preflight_check(path, start_line, end_line, new_content)
    preflight_warnings = preflight.get("warnings", [])

    total_lines = len(original_lines)
    start = _lineno_safety(original_lines, start_line)

    if end_line is not None:
        end = _lineno_safety(original_lines, end_line)
        if start > end:
            start, end = end, start
        if new_content:
            modo = "reemplazar"
            new_lines = new_content.splitlines(keepends=True)
            if new_lines and not new_lines[-1].endswith('\n') and original_lines and original_lines[-1].endswith('\n'):
                new_lines[-1] += '\n'
            result_lines = original_lines[:start-1] + new_lines + original_lines[end:]
        else:
            modo = "eliminar"
            result_lines = original_lines[:start-1] + original_lines[end:]
            deleted_defs = []
            try:
                import ast
                for line in ''.join(original_lines[start-1:end]).splitlines():
                    stripped = line.strip()
                    if stripped.startswith('def ') or stripped.startswith('async def '):
                        name_part = stripped.split('(')[0] if '(' in stripped else stripped.split(':')[0]
                        name = name_part.replace('def ', '').replace('async ', '').strip()
                        if name and not name.startswith('__'):
                            deleted_defs.append(name)
                    elif stripped.startswith('class '):
                        name = stripped.split('(')[0].split(':')[0].replace('class ', '').strip()
                        if name and not name.startswith('__'):
                            deleted_defs.append(name)
            except Exception:
                pass
    elif new_content:
        modo = "insertar"
        new_lines = new_content.splitlines(keepends=True)
        if new_lines and not new_lines[-1].endswith('\n') and original_lines and original_lines[-1].endswith('\n'):
            new_lines[-1] += '\n'
        result_lines = original_lines[:start-1] + new_lines + original_lines[start-1:]
    else:
        return "[ERROR] Debes proporcionar new_content o end_line (o ambos)."

    backup_path = create_backup(path)
    new_content_full = ''.join(result_lines)

    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content_full)
    except Exception as e:
        if backup_path:
            rollback(path, backup_path)
        return f"[ERROR] No se pudo escribir (rollback aplicado): {e}"

    pf = postflight_check(path, new_content_full)
    if not pf["ok"] and backup_path:
        rollback(path, backup_path)
        error_detail = "; ".join(pf["errors"][:3])
        return f"[ERROR] Post-flight falló (rollback aplicado): {error_detail}"

    diff = len(result_lines) - total_lines
    summary = f"✅ Editado: {path}\n"
    summary += f"   Modo: {modo} | Lineas: {start}"
    if end_line is not None:
        summary += f"-{end}"
    summary += f"\n   Lineas resultantes: {len(result_lines)} ({diff:+d})"

    if pf["ok"]:
        summary += f"\n   ✅ Post-flight OK"
    elif pf["warnings"]:
        for w in pf["warnings"][:3]:
            summary += f"\n   ⚡ {w}"

    if preflight_warnings:
        for w in preflight_warnings[:3]:
            summary += f"\n   ⚠️ Pre-flight: {w}"

    if modo == "eliminar" and deleted_defs:
        try:
            for def_name in deleted_defs:
                impact_result = _run_impact_analysis(def_name, path)
                if impact_result and "Sin dependencias" not in impact_result:
                    summary += f"\n{impact_result}"
        except Exception:
            pass

    return AwaitableText(summary)


def run(**kwargs: Any) -> str:
    path = kwargs.get("path", "").strip()
    start_line = int(kwargs.get("start_line", 0))
    end_line = kwargs.get("end_line")
    if end_line is not None:
        end_line = int(end_line)
    new_content = kwargs.get("new_content", "")
    arch_check = kwargs.get("arch_check", True)
    verbose = kwargs.get("verbose", True)
    if not path:
        return "[ERROR] Proporciona una ruta de archivo."

    path, err = resolve_and_validate_path(path)
    if err:
        return err

    summary = _edit_file_sync(path, start_line, end_line, new_content)
    if not summary.startswith("✅"):
        return AwaitableText(summary)

    # ── ARCH CHECK (post-hook, async doble check) ─────────────────────
    if arch_check:
        try:
            from src.tools._arch_checker import quick_check
            arch_result = quick_check(path)
            if verbose or "🔴" in arch_result or "VIOLACIÓN" in arch_result:
                summary += f"\n   {arch_result}"
        except Exception:
            pass

    return summary
