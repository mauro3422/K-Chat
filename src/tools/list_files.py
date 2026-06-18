"""list_files: lista archivos con informacion detallada.

Sigue el patron Lego: DEFINITION + run().
"""
import ast
import fnmatch
import logging
import os
import sys
from pathlib import Path
from typing import Any

from src.tools._path_helpers import resolve_and_validate_path
from src.tools._analyzers import (
    detect_language,
    icon,
    build_summary,
    analyze_python,
    analyze_javascript,
    analyze_markdown,
    analyze_html,
    analyze_css,
)
from src.utils.async_utils import run_in_thread

logger = logging.getLogger(__name__)
DEFINITION = {
    "type": "function",
    "function": {
        "name": "list_files",
        "description": (
            "Lista archivos en un directorio con informacion detallada: "
            "lineas de codigo, lenguaje, funciones definidas, clases, imports. "
            "Analiza Python con AST (funciones, clases, imports) y otros lenguajes "
            "con regex (JS/TS, HTML, Markdown). "
            "Ideal para tener una vista rapida de la estructura del proyecto."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directorio a listar (default: ~/proyectos)",
                    "default": "~/proyectos"
                },
                "depth": {
                    "type": "integer",
                    "description": "Profundidad de subdirectorios (default: 1, max: 3, 0 = solo el directorio actual)",
                    "default": 1
                },
                "pattern": {
                    "type": "string",
                    "description": "Filtro glob opcional (ej: '*.py', '*.md', '*test*'). Vacio = todos los archivos.",
                    "default": ""
                },
                "show_imports": {
                    "type": "boolean",
                    "description": "Mostrar imports/requires del archivo (default: false)",
                    "default": False
                }
            },
            "required": []
        }
    }
}

# Limites
MAX_FILE_SIZE = 500 * 1024  # 500KB max para analisis
MAX_LINES_ANALYSIS = 10000  # no analizar archivos con mas de 10000 lineas
MAX_FILES_LISTED = 200  # limite total de archivos a mostrar


# Directorios a ignorar siempre
SKIP_DIRS = frozenset({
    '__pycache__', 'node_modules', '.git', '.svn', '.hg',
    'venv', '.venv', 'env', '.env', 'dist', 'build',
    '.next', '.nuxt', '.turbo', 'coverage', '.pytest_cache',
})

def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    kb = size / 1024
    if kb < 1024:
        return f"{kb:.1f}K"
    mb = kb / 1024
    return f"{mb:.1f}M"


def _analyze_file(filepath: str, show_imports: bool) -> dict:
    """Analiza un archivo individual y devuelve metadata."""
    ext = os.path.splitext(filepath)[1].lower()
    lang_name, lang_type = detect_language(filepath)

    result: dict = {
        'name': os.path.basename(filepath),
        'lines': 0,
        'size': 0,
        'language': lang_name,
        'icon': icon(lang_type),
        'summary': '',
        'imports': [],
    }

    try:
        st = os.stat(filepath)
        result['size'] = st.st_size
    except OSError:
        result['summary'] = '(no stats)'
        return result

    # Archivos muy grandes: solo info basica
    if result['size'] > MAX_FILE_SIZE:
        result['summary'] = f'({_format_size(result["size"])}, >500K, analisis omitido)'
        return result

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception:
        result['summary'] = '(no se pudo leer)'
        return result

    # Contar lineas
    lines = content.splitlines()
    result['lines'] = len(lines)
    if result['lines'] == 0:
        return result

    # Si es muy largo, solo contamos lineas
    if result['lines'] > MAX_LINES_ANALYSIS:
        result['summary'] = f'({result["lines"]} lines, >10K, analisis omitido)'
        return result

    # Analisis por lenguaje
    analysis: dict = {}
    if ext == '.py':
        analysis = analyze_python(content)
    elif ext in ('.js', '.jsx', '.ts', '.tsx', '.mjs'):
        analysis = analyze_javascript(content)
    elif ext in ('.md', '.markdown'):
        analysis = analyze_markdown(content)
    elif ext in ('.html', '.htm'):
        analysis = analyze_html(content)
    elif ext in ('.css', '.scss'):
        analysis = analyze_css(content)

    summary, imports_list = build_summary(analysis, show_imports)
    result['summary'] = summary
    result['imports'] = imports_list
    return result


def _format_file_entry(prefix: str, fname: str, info: dict, show_imports: bool, import_prefix: str) -> str:
    """Formatea una entrada de archivo individual con su metadata."""
    line_str = f"{info['lines']} lines" if info['lines'] else "?"
    smry = f"  {info['summary']}" if info['summary'] else ""
    output = f"{prefix}{fname:<35} {line_str:>12} {info['icon']} {info['language']}{smry}\n"
    if show_imports and info['imports']:
        for imp in info['imports']:
            output += f"{import_prefix}{imp}\n"
    return output


def _categorize_entries(path: str, entries: list[str], pattern: str) -> tuple[list[str], list[str]]:
    """Separa entradas del directorio en subdirectorios y archivos, aplicando filtros."""
    dirs: list[str] = []
    files: list[str] = []
    for entry in entries:
        full = os.path.join(path, entry)
        if entry.startswith('.'):
            continue
        if os.path.isdir(full) and entry not in SKIP_DIRS:
            _, err = resolve_and_validate_path(full)
            if not err:
                dirs.append(entry)
        elif os.path.isfile(full):
            _, err = resolve_and_validate_path(full)
            if err:
                continue
            if not pattern or fnmatch.fnmatch(entry, pattern):
                files.append(entry)
    return dirs, files


def _walk_directory(
    path: str,
    depth: int,
    pattern: str,
    show_imports: bool,
    current_depth: int = 0,
    file_count: int = 0,
) -> tuple[str, int]:
    """Recorre el directorio recursivamente y devuelve el texto formateado + contador."""
    if file_count > MAX_FILES_LISTED:
        return '', file_count

    indent = '  ' * current_depth
    sub_indent = '  ' * (current_depth + 1)
    basename = os.path.basename(path) or path

    try:
        entries = sorted(os.listdir(path))
    except PermissionError:
        return f"{indent}📁 {basename}/ (permiso denegado)\n", file_count
    except FileNotFoundError:
        return f"{indent}[ERROR] No existe: {path}\n", file_count
    except NotADirectoryError:
        info = _analyze_file(path, show_imports)
        file_count += 1
        output = _format_file_entry(f"{indent}📄 ", basename, info, show_imports, f"{indent}  import: ")
        return output, file_count

    dirs, files = _categorize_entries(path, entries, pattern)

    output = f"{indent}📁 {basename}/ ({len(dirs)} dirs, {len(files)} files)\n"

    for fname in files:
        if file_count > MAX_FILES_LISTED:
            output += f"{sub_indent}... (limite de {MAX_FILES_LISTED} archivos alcanzado)\n"
            return output, file_count

        fpath = os.path.join(path, fname)
        _, err = resolve_and_validate_path(fpath)
        if err:
            continue
        info = _analyze_file(fpath, show_imports)
        file_count += 1
        output += _format_file_entry(f"{sub_indent}├── ", fname, info, show_imports, f"{sub_indent}│   import: ")

    if current_depth < depth:
        for dname in dirs:
            if file_count > MAX_FILES_LISTED:
                return output, file_count
            dpath = os.path.join(path, dname)
            resolved_dpath, err = resolve_and_validate_path(dpath)
            if err:
                continue
            child_output, file_count = _walk_directory(
                resolved_dpath, depth, pattern, show_imports, current_depth + 1, file_count
            )
            output += child_output

    return output, file_count


async def run(**kwargs: Any) -> str:
    path = kwargs.get("path", "~/proyectos")
    depth = min(int(kwargs.get("depth", 1)), 3)  # max depth 3
    pattern = kwargs.get("pattern", "").strip()
    show_imports = bool(kwargs.get("show_imports", False))

    resolved_path, err = resolve_and_validate_path(path)
    if err:
        return err



    if not await run_in_thread(os.path.exists, resolved_path):
        return f"[ERROR] El path '{path}' no existe."

    output, count = await run_in_thread(_walk_directory, resolved_path, depth, pattern, show_imports)

    # Limitar output total
    if len(output) > 30000:
        output = output[:30000] + "\n...[truncado a 30000 caracteres]"

    return output if output else f"(directorio vacio: {path})"
