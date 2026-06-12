"""list_files: vista panorámica de archivos con análisis inteligente.

Analiza archivos Python con AST y otros lenguajes con regex.
Detecta funciones, clases, imports/exports, headers, estructura HTML.
"""
import ast
import fnmatch
import logging
import os
import re
from typing import Any

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
MAX_IMPORTS_SHOWN = 12
MAX_FUNCTIONS_SHOWN = 10
MAX_CLASSES_SHOWN = 6
MAX_FILES_LISTED = 200  # limite total de archivos a mostrar

# Mapa de lenguajes
LANGUAGE_MAP: dict[str, tuple[str, str]] = {
    '.py': ('Python', 'snake'),
    '.js': ('JavaScript', 'js'),
    '.jsx': ('React JSX', 'react'),
    '.ts': ('TypeScript', 'ts'),
    '.tsx': ('React TSX', 'react'),
    '.mjs': ('ES Module', 'js'),
    '.html': ('HTML', 'html'),
    '.htm': ('HTML', 'html'),
    '.css': ('CSS', 'css'),
    '.scss': ('SCSS', 'css'),
    '.md': ('Markdown', 'md'),
    '.json': ('JSON', 'data'),
    '.yaml': ('YAML', 'data'),
    '.yml': ('YAML', 'data'),
    '.sh': ('Shell', 'shell'),
    '.bash': ('Shell', 'shell'),
    '.sql': ('SQL', 'db'),
    '.txt': ('Texto', 'text'),
    '.toml': ('TOML', 'data'),
    '.cfg': ('Config', 'cfg'),
    '.ini': ('INI', 'cfg'),
    '.env': ('Env', 'cfg'),
    '.gitignore': ('Git', 'git'),
    '.dockerignore': ('Docker', 'docker'),
    '.pyi': ('Python Stub', 'snake'),
    '.svg': ('SVG', 'image'),
    '.xml': ('XML', 'data'),
    '.lock': ('Lock', 'lock'),
}

# Regex para JS/TS
_JS_FUNC = re.compile(
    r'(?:function\s+(\w+)|'
    r'(\w+)\s*[=:]\s*(?:async\s+)?function|'
    r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(|'
    r'(?:export\s+)?(?:default\s+)?function\s+(\w+))'
)
_JS_CLASS = re.compile(r'(?:export\s+)?(?:default\s+)?class\s+(\w+)')
_JS_IMPORT_FROM = re.compile(r"from\s+['\"]([^'\"]+)['\"]")
_JS_REQUIRE = re.compile(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
_JS_EXPORT = re.compile(r'export\s+(?:default\s+)?(?:function|class|const|let|var)\s+(\w+)')

# Regex para headers MD
_MD_HEADER = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

# Regex para estructura HTML
_HTML_TAG = re.compile(r'<(head|body|script|style|main|nav|header|footer|section|article|aside)\b')

# Regex para CSS
_CSS_IMPORT = re.compile(r"""@import\s+['\"]?([^;'\"]+)""")

# Directorios a ignorar siempre
SKIP_DIRS = frozenset({
    '__pycache__', 'node_modules', '.git', '.svn', '.hg',
    'venv', '.venv', 'env', '.env', 'dist', 'build',
    '.next', '.nuxt', '.turbo', 'coverage', '.pytest_cache',
})

# Archivos a ignorar siempre
SKIP_FILES_PREFIX = frozenset({'.', '__pycache__'})


def _detect_language(filename: str) -> tuple[str, str]:
    """Detecta lenguaje por extensión."""
    ext = os.path.splitext(filename)[1].lower()
    basename = os.path.basename(filename).lower()
    if basename in ('.gitignore',):
        return ('Git', 'git')
    if basename in ('.dockerignore',):
        return ('Docker', 'docker')
    if basename in ('dockerfile',):
        return ('Docker', 'docker')
    if basename in ('makefile',):
        return ('Make', 'shell')
    return LANGUAGE_MAP.get(ext, ('Unknown', 'unknown'))


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    kb = size / 1024
    if kb < 1024:
        return f"{kb:.1f}K"
    mb = kb / 1024
    return f"{mb:.1f}M"


def _icon(lang_type: str) -> str:
    icons = {
        'snake': '🐍', 'js': '🟨', 'ts': '🔷', 'react': '⚛️',
        'html': '🌐', 'css': '🎨', 'md': '📝', 'data': '📋',
        'shell': '🐚', 'db': '🗃️', 'text': '📄', 'cfg': '⚙️',
        'git': '🔀', 'docker': '🐳', 'image': '🖼️', 'lock': '🔒',
        'unknown': '📄',
    }
    return icons.get(lang_type, '📄')


def _analyze_python(content: str) -> dict:
    """Analiza Python con AST."""
    result: dict = {'functions': [], 'classes': [], 'async_funcs': [], 'imports': []}
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                result['functions'].append(node.name)
            elif isinstance(node, ast.AsyncFunctionDef):
                result['async_funcs'].append(node.name)
            elif isinstance(node, ast.ClassDef):
                result['classes'].append(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    result['imports'].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                for alias in node.names:
                    full = f"{module}.{alias.name}" if module else alias.name
                    if full not in result['imports']:
                        result['imports'].append(full)
    except SyntaxError:
        pass  # archivo con errores de sintaxis, ignoramos el analisis
    return result


def _analyze_javascript(content: str) -> dict:
    """Analiza JavaScript/TypeScript con regex."""
    result: dict = {'functions': [], 'classes': [], 'imports': [], 'exports': []}
    seen_funcs: set = set()
    for match in _JS_FUNC.finditer(content):
        for g in match.groups():
            if g and g not in seen_funcs:
                seen_funcs.add(g)
                result['functions'].append(g)
    for match in _JS_CLASS.finditer(content):
        cls_name = match.group(1)
        if cls_name not in result['classes']:
            result['classes'].append(cls_name)
    for match in _JS_EXPORT.finditer(content):
        ename = match.group(1)
        if ename not in result['exports']:
            result['exports'].append(ename)
    for match in _JS_IMPORT_FROM.finditer(content):
        imp = match.group(1)
        if imp not in result['imports']:
            result['imports'].append(imp)
    for match in _JS_REQUIRE.finditer(content):
        imp = match.group(1)
        if imp not in result['imports']:
            result['imports'].append(imp)
    return result


def _analyze_markdown(content: str) -> dict:
    """Analiza headers de Markdown."""
    result: dict = {'headers': []}
    for match in _MD_HEADER.finditer(content):
        level = len(match.group(1))
        title = match.group(2).strip()
        result['headers'].append(f"{'#' * level} {title}")
    return result


def _analyze_html(content: str) -> dict:
    """Analiza estructura HTML."""
    result: dict = {'tags': []}
    seen: set = set()
    for match in _HTML_TAG.finditer(content):
        tag = match.group(1)
        if tag not in seen:
            seen.add(tag)
            result['tags'].append(tag)
    return result


def _analyze_css(content: str) -> dict:
    """Analiza imports CSS."""
    result: dict = {'imports': []}
    for match in _CSS_IMPORT.finditer(content):
        result['imports'].append(match.group(1))
    return result


def _build_summary(analysis: dict, show_imports: bool) -> tuple[str, list[str]]:
    """Construye el resumen legible y lista de imports."""
    parts = []
    imports_list = []

    if analysis.get('functions'):
        funcs = analysis['functions'][:MAX_FUNCTIONS_SHOWN]
        extra = len(analysis['functions']) - MAX_FUNCTIONS_SHOWN
        s = ', '.join(funcs)
        if extra > 0:
            s += f" (+{extra})"
        parts.append(f"fn: {s}")

    if analysis.get('async_funcs'):
        parts.append(f"async: {', '.join(analysis['async_funcs'][:4])}")

    if analysis.get('classes'):
        cls = analysis['classes'][:MAX_CLASSES_SHOWN]
        extra = len(analysis['classes']) - MAX_CLASSES_SHOWN
        s = ', '.join(cls)
        if extra > 0:
            s += f" (+{extra})"
        parts.append(f"cls: {s}")

    if analysis.get('exports'):
        parts.append(f"export: {', '.join(analysis['exports'][:6])}")

    if analysis.get('headers'):
        h = analysis['headers'][:5]
        extra = len(analysis['headers']) - 5
        s = ', '.join(h)
        if extra > 0:
            s += f" (+{extra})"
        parts.append(f"#: {s}")

    if analysis.get('tags'):
        parts.append(f"tags: {', '.join(analysis['tags'])}")

    if show_imports and analysis.get('imports'):
        imports_list = analysis['imports'][:MAX_IMPORTS_SHOWN]
        extra = len(analysis['imports']) - MAX_IMPORTS_SHOWN
        if extra > 0:
            imports_list.append(f"... (+{extra} more)")

    return ' | '.join(parts) if parts else '', imports_list


def _analyze_file(filepath: str, show_imports: bool) -> dict:
    """Analiza un archivo individual y devuelve metadata."""
    ext = os.path.splitext(filepath)[1].lower()
    lang_name, lang_type = _detect_language(filepath)

    result: dict = {
        'name': os.path.basename(filepath),
        'lines': 0,
        'size': 0,
        'language': lang_name,
        'icon': _icon(lang_type),
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
        analysis = _analyze_python(content)
    elif ext in ('.js', '.jsx', '.ts', '.tsx', '.mjs'):
        analysis = _analyze_javascript(content)
    elif ext in ('.md', '.markdown'):
        analysis = _analyze_markdown(content)
    elif ext in ('.html', '.htm'):
        analysis = _analyze_html(content)
    elif ext in ('.css', '.scss'):
        analysis = _analyze_css(content)

    summary, imports_list = _build_summary(analysis, show_imports)
    result['summary'] = summary
    result['imports'] = imports_list
    return result


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
        # Si es un archivo, lo analizamos directamente
        info = _analyze_file(path, show_imports)
        file_count += 1
        size_str = _format_size(info['size'])
        line_str = f"{info['lines']} lines" if info['lines'] else "?"
        smry = f"  {info['summary']}" if info['summary'] else ""
        output = f"{indent}📄 {basename:<35} {line_str:>12} {info['icon']} {info['language']}{smry}\n"
        if show_imports and info['imports']:
            for imp in info['imports']:
                output += f"{indent}  import: {imp}\n"
        return output, file_count

    # Separar directorios y archivos
    dirs = []
    files = []
    for entry in entries:
        full = os.path.join(path, entry)
        if entry.startswith('.'):
            continue
        if os.path.isdir(full) and entry not in SKIP_DIRS:
            dirs.append(entry)
        elif os.path.isfile(full) and not entry.startswith('.'):
            if pattern:
                if fnmatch.fnmatch(entry, pattern):
                    files.append(entry)
            else:
                files.append(entry)

    output = f"{indent}📁 {basename}/ ({len(dirs)} dirs, {len(files)} files)\n"

    # Archivos
    for fname in files:
        if file_count > MAX_FILES_LISTED:
            output += f"{sub_indent}... (limite de {MAX_FILES_LISTED} archivos alcanzado)\n"
            return output, file_count

        fpath = os.path.join(path, fname)
        info = _analyze_file(fpath, show_imports)
        file_count += 1
        size_str = _format_size(info['size'])
        line_str = f"{info['lines']} lines" if info['lines'] else "?"
        smry = f"  {info['summary']}" if info['summary'] else ""
        output += f"{sub_indent}├── {fname:<35} {line_str:>12} {info['icon']} {info['language']}{smry}\n"
        if show_imports and info['imports']:
            for imp in info['imports']:
                output += f"{sub_indent}│   import: {imp}\n"

    # Subdirectorios (recursivo)
    if current_depth < depth:
        for dname in dirs:
            if file_count > MAX_FILES_LISTED:
                return output, file_count
            dpath = os.path.join(path, dname)
            child_output, file_count = _walk_directory(
                dpath, depth, pattern, show_imports, current_depth + 1, file_count
            )
            output += child_output

    return output, file_count


def run(**kwargs: Any) -> str:
    path = os.path.expanduser(kwargs.get("path", "~/proyectos"))
    depth = min(int(kwargs.get("depth", 1)), 3)  # max depth 3
    pattern = kwargs.get("pattern", "").strip()
    show_imports = bool(kwargs.get("show_imports", False))

    if not os.path.exists(path):
        return f"[ERROR] El path '{path}' no existe."

    output, count = _walk_directory(path, depth, pattern, show_imports)

    # Limitar output total
    if len(output) > 30000:
        output = output[:30000] + "\n...[truncado a 30000 caracteres]"

    return output if output else f"(directorio vacio: {path})"
