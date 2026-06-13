"""search_files: búsqueda inteligente de texto en archivos.

Busca patrones en archivos del proyecto con contexto, detección de
funciones/clases (vía AST para Python), y stats. Similar a grep pero
formateado para lectura rápida.
"""
import ast
import logging
import os
import re
from typing import Any

from src.tools._path_helpers import resolve_and_validate_path
from src.tools._analyzers import find_function_at_line, matches_file_pattern

logger = logging.getLogger(__name__)

DEFINITION = {
    "type": "function",
    "function": {
        "name": "search_files",
        "description": (
            "Busca un patron de texto en archivos del proyecto. "
            "Muestra las lineas donde aparece con contexto, "
            "detecta en que funcion/clase esta cada coincidencia (Python con AST), "
            "y muestra estadisticas. Similar a grep pero mas legible."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "El texto o patron a buscar (no es regex, es busqueda literal)"
                },
                "path": {
                    "type": "string",
                    "description": "Directorio donde buscar (default: ~/proyectos)",
                    "default": "~/proyectos"
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Filtro glob para archivos (ej: '*.py', '*.md', '*.{py,js}'). Vacio = todos.",
                    "default": ""
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Lineas de contexto antes y despues de cada coincidencia (default: 2, max: 10)",
                    "default": 2
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximo de coincidencias a mostrar (default: 50, max: 200)",
                    "default": 50
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Busqueda exacta (default: false = ignora mayusculas/minusculas)",
                    "default": False
                }
            },
            "required": ["pattern"]
        }
    }
}

MAX_FILE_SIZE = 500 * 1024
MAX_OUTPUT = 30000

SKIP_DIRS = frozenset({
    '__pycache__', 'node_modules', '.git', '.svn', '.hg',
    'venv', '.venv', 'env', '.env', 'dist', 'build',
    '.next', '.nuxt', '.turbo', 'coverage', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', '__pycache__',
})

def _should_skip_dir(name: str) -> bool:
    return name.startswith('.') or name in SKIP_DIRS

def _find_matches_in_file(
    filepath: str,
    pattern: str,
    context_lines: int,
    max_results: int,
    case_sensitive: bool,
) -> dict:
    """Busca coincidencias en un archivo y devuelve resultados formateados."""
    result: dict = {
        'filepath': filepath,
        'matches': [],
        'count': 0,
        'error': None,
    }

    # Verificar tamaño
    try:
        size = os.path.getsize(filepath)
    except OSError as e:
        result['error'] = str(e)
        return result

    if size > MAX_FILE_SIZE:
        result['error'] = f"archivo demasiado grande ({size / 1024:.0f}K)"
        return result

    # Leer archivo
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except Exception as e:
        result['error'] = f"no se pudo leer: {e}"
        return result

    # Buscar
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(re.escape(pattern), flags)
    except re.error:
        result['error'] = f"patron invalido"
        return result

    # AST para Python
    tree = None
    if filepath.endswith('.py'):
        try:
            tree = ast.parse(''.join(lines))
        except SyntaxError:
            pass  # si falla el parseo, seguimos sin AST

    # Encontrar matches
    match_lines = []
    for i, line in enumerate(lines, 1):
        if regex.search(line):
            match_lines.append(i)
            if len(match_lines) >= max_results:
                break

    if not match_lines:
        return result  # sin matches

    result['count'] = len(match_lines)
    match_set = set(match_lines)

    # Construir contexto para cada match
    for _ in range(len(match_lines)):
        ml = match_lines[_]
        start = max(1, ml - context_lines)
        end = min(len(lines), ml + context_lines)

        # Detectar funcion/clase contenedora
        container = find_function_at_line(tree, ml) if tree else None

        context = []
        for ln in range(start, end + 1):
            line_text = lines[ln - 1].rstrip('\n')
            marker = '→' if ln in match_set else ' '
            context.append({
                'line': ln,
                'text': line_text,
                'is_match': ln in match_set,
            })

        result['matches'].append({
            'line': ml,
            'container': container,
            'context_lines': context,
        })

    return result

def _format_match(filepath: str, data: dict) -> str:
    """Formatea las coincidencias de un archivo."""
    basename = os.path.basename(filepath)
    short_path = filepath.replace(os.path.expanduser('~'), '~')

    lines = [f"\n📄 {short_path}  ({data['count']} match{'es' if data['count'] != 1 else ''})"]

    for m in data['matches']:
        if m.get('container'):
            lines.append(f"   ┌─ {m['container']}")

        for ctx in m['context_lines']:
            marker = '→' if ctx['is_match'] else ' '
            line_str = f"   {marker} L:{ctx['line']:<5} {ctx['text']}"
            # Truncar líneas muy largas
            if len(line_str) > 150:
                line_str = line_str[:147] + "..."
            lines.append(line_str)

        # Separador entre matches
        if m != data['matches'][-1]:
            lines.append(f"   ┃")

    return '\n'.join(lines)

def _walk_and_search(
    path: str,
    pattern: str,
    file_pattern: str,
    context_lines: int,
    max_results: int,
    case_sensitive: bool,
    total_found: int = 0,
) -> tuple[str, int, int]:
    """Recorre directorios buscando coincidencias."""
    output_parts = []
    total_files = 0
    total_matches = 0
    dirs_to_check = [path]
    checked_files = 0

    for current_dir in dirs_to_check:
        if total_found > 0 and total_matches >= max_results:
            break

        try:
            entries = sorted(os.listdir(current_dir))
        except (PermissionError, FileNotFoundError):
            continue

        files = []
        dirs = []
        for entry in entries:
            full = os.path.join(current_dir, entry)
            if os.path.isdir(full):
                if not _should_skip_dir(entry):
                    _, err = resolve_and_validate_path(full)
                    if not err:
                        dirs.append(full)
            elif os.path.isfile(full):
                if not entry.startswith('.'):
                    _, err = resolve_and_validate_path(full)
                    if err:
                        continue
                    if matches_file_pattern(entry, file_pattern):
                        files.append(full)

        # Leer archivos
        for fpath in files:
            if total_matches >= max_results:
                break
            checked_files += 1

            data = _find_matches_in_file(
                fpath, pattern, context_lines,
                max_results - total_matches, case_sensitive
            )
            if data['error']:
                continue
            if data['count'] > 0:
                formatted = _format_match(fpath, data)
                output_parts.append(formatted)
                total_files += 1
                total_matches += data['count']

        # Agregar subdirectorios para procesar
        dirs_to_check.extend(dirs)

        if len(output_parts) > 0 and len('\n'.join(output_parts)) > MAX_OUTPUT * 0.8:
            break

    return '\n'.join(output_parts), total_files, total_matches

def run(**kwargs: Any) -> str:
    pattern = kwargs.get("pattern", "").strip()
    path = kwargs.get("path", "~/proyectos")
    file_pattern = kwargs.get("file_pattern", "").strip()
    context_lines = min(int(kwargs.get("context_lines", 2)), 10)
    max_results = min(int(kwargs.get("max_results", 50)), 200)
    case_sensitive = bool(kwargs.get("case_sensitive", False))

    if not pattern:
        return "[ERROR] Debes proporcionar un patron de busqueda."

    path, err = resolve_and_validate_path(path)
    if err:
        return err

    if not os.path.isdir(path):
        return f"[ERROR] El directorio '{path}' no existe."

    # Output header
    flags_str = " (exacta)" if case_sensitive else " (sin mayusculas)"
    file_str = f" en {file_pattern}" if file_pattern else ""
    output = f"🔍 Buscando \"{pattern}\"{file_str} en {path}{flags_str}"

    results, total_files, total_matches = _walk_and_search(
        path, pattern, file_pattern,
        context_lines, max_results, case_sensitive,
    )

    if not results:
        output += "\n\n📭 Sin coincidencias."
        return output

    output += "\n" + "━" * 50
    output += results
    output += f"\n\n{'━' * 50}"
    output += f"\n🎯 {total_files} archivo{'s' if total_files != 1 else ''}, {total_matches} coincidencia{'s' if total_matches != 1 else ''}"

    if len(output) > MAX_OUTPUT:
        output = output[:MAX_OUTPUT] + "\n...[truncado]"

    return output
