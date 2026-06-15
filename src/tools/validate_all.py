"""validate_all: valida sintaxis de múltiples archivos en una sola llamada.

Usa los validadores de _validators.py según la extensión.
Sigue el patrón Lego: DEFINITION + run().
"""
import os
import logging
from typing import Any

from src.tools._path_helpers import resolve_and_validate_path
from src.tools._validators import validate_file

logger = logging.getLogger(__name__)

MAX_FILES = 20

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "validate_all",
        "description": (
            "Valida la sintaxis de MULTIPLES archivos Python, JS, JSON, HTML, CSS en UNA sola llamada. "
            "Usa los validadores internos segun la extension de cada archivo. "
            "Devuelve un resumen con cuantos pasaron, fallaron o fueron omitidos. "
            "Opcionalmente verifica reglas arquitectónicas (modo architecture)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de rutas de archivos a validar. Max 20 archivos."
                },
                "path": {
                    "type": "string",
                    "description": "Directorio a escanear (profundidad 1) en lugar de lista de archivos. Opcional si ya pasaste 'files'."
                },
                "pattern": {
                    "type": "string",
                    "description": "Filtro glob para archivos (ej: '*.py', '*.{py,js}'). Solo si usas 'path'.",
                    "default": ""
                },
                "architecture": {
                    "type": "boolean",
                    "description": "Si True, también verifica reglas arquitectónicas Legos (upward coupling, framework imports, etc.). Default: False.",
                    "default": False
                }
            }
        }
    }
}


def _find_files(directory: str, pattern: str = "") -> list[str]:
    """Busca archivos en un directorio (profundidad 1) con filtro opcional."""
    import fnmatch
    results = []
    try:
        for f in sorted(os.listdir(directory)):
            fpath = os.path.join(directory, f)
            if os.path.isfile(fpath):
                if pattern and not fnmatch.fnmatch(f, pattern):
                    continue
                results.append(fpath)
    except Exception as e:
        logger.warning("Error listando %s: %s", directory, e)
    return results


def run(**kwargs: Any) -> str:
    files: list = kwargs.get("files", [])
    directory: str | None = kwargs.get("path")
    pattern: str = kwargs.get("pattern", "")
    arch_check: bool = kwargs.get("architecture", False)
    # Si no hay lista de archivos, escanear directorio
    if not files and directory:
        resolved_dir, err = resolve_and_validate_path(directory)
        if err:
            return f"[ERROR] {err}"
        if not os.path.isdir(resolved_dir):
            return f"[ERROR] '{directory}' no es un directorio valido."
        files = _find_files(resolved_dir, pattern)
        if not files:
            return f"[INFO] No se encontraron archivos{' con patrón '+pattern if pattern else ''} en {directory}."

    if not files or not isinstance(files, (list, tuple)):
        return "[ERROR] Debes proporcionar 'files' (lista) o 'path' (directorio a escanear)."

    # Run architecture check first (independent of file limit)
    arch_output = ""
    if arch_check:
        try:
            from src.tools._arch_checker import check_directory, check_file
            if directory:
                resolved_dir, _ = resolve_and_validate_path(directory)
                if resolved_dir and os.path.isdir(resolved_dir):
                    report = check_directory(resolved_dir, recursive=False)
                    arch_output = f"\n{report.summary()}"
            elif files:
                all_violations = []
                for fpath in files[:MAX_FILES]:
                    resolved, _ = resolve_and_validate_path(str(fpath))
                    if resolved and os.path.isfile(resolved):
                        violations = check_file(resolved)
                        all_violations.extend(violations)
                if all_violations:
                    arch_output = f"\n🏛️ ARCHITECTURE CHECK — {len(all_violations)} violación(es):\n"
                    for v in all_violations:
                        arch_output += f"   {v}\n"
                else:
                    arch_output = f"\n🏛️ ARCHITECTURE CHECK — ✅ Sin violaciones arquitectónicas\n"
        except Exception:
            pass

    if len(files) > MAX_FILES:
        files = files[:MAX_FILES]
        truncated = True
    else:
        truncated = False
    results: list[dict[str, Any]] = []
    passed = failed = skipped = 0
    passed = failed = skipped = 0

    for fpath in files:
        # Resolver ruta si es un path directo
        resolved, err = resolve_and_validate_path(str(fpath))
        if err or not os.path.isfile(resolved):
            results.append({"file": fpath, "status": "error", "message": "Archivo no encontrado"})
            failed += 1
            continue

        try:
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            results.append({"file": fpath, "status": "error", "message": f"No se pudo leer: {e}"})
            failed += 1
            continue

        validation = validate_file(resolved, content)
        status = validation.get("status", "skipped")

        if status == "ok":
            passed += 1
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1

        results.append({
            "file": fpath,
            "status": status,
            "message": validation.get("message", ""),
            "line": validation.get("line"),
        })

    # Armar resumen
    summary = (
        f"📊 VALIDACION COMPLETA ({len(files)} archivos)\n"
        f"   ✅ Pasaron: {passed}\n"
        f"   ❌ Fallaron: {failed}\n"
        f"   ⏭️  Omitidos: {skipped}\n\n"
    )

    # Detalle de fallos
    failures = [r for r in results if r["status"] == "error"]
    if failures:
        summary += "❌ ERRORES:\n"
        for r in failures:
            line_info = f" (linea {r['line']})" if r.get("line") else ""
            summary += f"  - {r['file']}{line_info}: {r['message']}\n"

    # Detalle de omitidos
    # Detalle de omitidos
    skips = [r for r in results if r["status"] == "skipped"]
    if skips:
        summary += f"\n⏭️  OMITIDOS ({len(skips)}):\n"
        for r in skips[:10]:
            summary += f"  - {r['file']}: {r['message']}\n"

    # ── ARCHITECTURE CHECK (optional) ─────────────────────────────
    if arch_check:
        try:
            from src.tools._arch_checker import check_directory, check_file
            # If we have a directory, check it; otherwise check individual files
            if directory:
                resolved_dir, _ = resolve_and_validate_path(directory)
                if resolved_dir and os.path.isdir(resolved_dir):
                    report = check_directory(resolved_dir, recursive=False)
                    summary += f"\n{report.summary()}"
            elif files:
                # Check each file individually
                all_violations = []
                for fpath in files[:MAX_FILES]:
                    resolved, _ = resolve_and_validate_path(str(fpath))
                    if resolved and os.path.isfile(resolved):
                        violations = check_file(resolved)
                        all_violations.extend(violations)
                if all_violations:
                    summary += f"\n🏛️ ARCHITECTURE CHECK — {len(all_violations)} violación(es):\n"
                    for v in all_violations:
                        summary += f"   {v}\n"
                else:
                    summary += f"\n🏛️ ARCHITECTURE CHECK — ✅ Sin violaciones arquitectónicas\n"
        except Exception:
            pass  # arch check is non-blocking

    return summary
