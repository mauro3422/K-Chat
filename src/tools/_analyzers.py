"""_analyzers: análisis de código compartido entre tools (list_files, search_files).

Language detection, AST analysis, regex patterns.
Reduce duplicación de lógica entre tools.
"""
import ast
import fnmatch
import logging
import os
import re
import sys
from typing import Any

logger = logging.getLogger(__name__)

# ─── Language Detection ───────────────────────────────────────────────

LANGUAGE_MAP: dict[str, tuple[str, str]] = {
    '.py': ('Python', 'snake'),
    '.pyi': ('Python Stub', 'snake'),
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
    '.svg': ('SVG', 'image'),
    '.xml': ('XML', 'data'),
    '.lock': ('Lock', 'lock'),
}

# Extensiones que pueden analizarse con AST (Python)
AST_EXTENSIONS = frozenset({'.py', '.pyi'})

# Extensiones que pueden analizarse con regex (JS/TS)
JS_EXTENSIONS = frozenset({'.js', '.jsx', '.ts', '.tsx', '.mjs'})


def _expand_brace_pattern(pattern: str) -> list[str]:
    """Expande un glob simple con llaves a una lista de patrones."""
    if "{" not in pattern or "}" not in pattern:
        return [pattern]

    start = pattern.find("{")
    end = pattern.find("}", start + 1)
    if start < 0 or end < 0 or end <= start + 1:
        return [pattern]

    prefix = pattern[:start]
    suffix = pattern[end + 1:]
    options = [part.strip() for part in pattern[start + 1:end].split(",") if part.strip()]
    if not options:
        return [pattern]
    return [f"{prefix}{opt}{suffix}" for opt in options]


def matches_file_pattern(filename: str, pattern: str) -> bool:
    """Evalúa un nombre de archivo contra un patrón glob simple."""
    pattern = pattern.strip()
    if not pattern:
        return True
    for expanded in _expand_brace_pattern(pattern):
        if fnmatch.fnmatch(filename, expanded):
            return True
    return False


def detect_language(filename: str) -> tuple[str, str]:
    """Detecta lenguaje por extensión. Devuelve (nombre_legible, tipo_icono)."""
    ext = os.path.splitext(filename)[1].lower()
    basename = os.path.basename(filename).lower()
    special = {
        '.gitignore': ('Git', 'git'),
        '.dockerignore': ('Docker', 'docker'),
        'dockerfile': ('Docker', 'docker'),
        'makefile': ('Make', 'shell'),
    }
    if basename in special:
        return special[basename]
    return LANGUAGE_MAP.get(ext, ('Unknown', 'unknown'))


# ─── Iconos ───────────────────────────────────────────────────────────

ICONS = {
    'snake': '🐍', 'js': '🟨', 'ts': '🔷', 'react': '⚛️',
    'html': '🌐', 'css': '🎨', 'md': '📝', 'data': '📋',
    'shell': '🐚', 'db': '🗃️', 'text': '📄', 'cfg': '⚙️',
    'git': '🔀', 'docker': '🐳', 'image': '🖼️', 'lock': '🔒',
    'unknown': '📄',
}


def icon(lang_type: str) -> str:
    return ICONS.get(lang_type, '📄')


# ─── Python AST Analysis ──────────────────────────────────────────────

def analyze_python(content: str) -> dict[str, Any]:
    """Analiza Python con AST. Devuelve funciones, clases, imports con lineas."""
    result: dict[str, Any] = {
        'functions': [], 'classes': [], 'async_funcs': [], 'imports': [],
    }
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                result['functions'].append({
                    'name': node.name,
                    'lineno': node.lineno,
                    'end_lineno': getattr(node, 'end_lineno', node.lineno),
                })
            elif isinstance(node, ast.AsyncFunctionDef):
                result['async_funcs'].append({
                    'name': node.name,
                    'lineno': node.lineno,
                    'end_lineno': getattr(node, 'end_lineno', node.lineno),
                })
            elif isinstance(node, ast.ClassDef):
                result['classes'].append({
                    'name': node.name,
                    'lineno': node.lineno,
                    'end_lineno': getattr(node, 'end_lineno', node.lineno),
                })
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name not in result['imports']:
                        result['imports'].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                for alias in node.names:
                    full = f"{module}.{alias.name}" if module else alias.name
                    if full not in result['imports']:
                        result['imports'].append(full)
    except SyntaxError:
        pass
    return result


def find_function_at_line(tree: ast.Module | None, line: int) -> str | None:
    """Dado un AST y un numero de linea, devuelve la funcion/clase contenedora."""
    if tree is None:
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = getattr(node, 'lineno', 0)
            end = getattr(node, 'end_lineno', sys.maxsize)
            if start <= line <= end:
                prefix = "cls" if isinstance(node, ast.ClassDef) else "fn"
                return f"{prefix} {node.name}:L{start}-L{end}"
    return None


# ─── JavaScript/TypeScript Regex Analysis ─────────────────────────────

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


def analyze_javascript(content: str) -> dict[str, Any]:
    """Analiza JavaScript/TypeScript con regex."""
    result: dict[str, Any] = {'functions': [], 'classes': [], 'imports': [], 'exports': []}
    seen_funcs: set = set()
    for match in _JS_FUNC.finditer(content):
        for g in match.groups():
            if g and g not in seen_funcs:
                seen_funcs.add(g)
                result['functions'].append(g)
    for match in _JS_CLASS.finditer(content):
        cls = match.group(1)
        if cls not in result['classes']:
            result['classes'].append(cls)
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


# ─── Markdown Analysis ────────────────────────────────────────────────

_MD_HEADER = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)


def analyze_markdown(content: str) -> dict[str, Any]:
    """Analiza headers de Markdown."""
    result: dict[str, Any] = {'headers': []}
    for match in _MD_HEADER.finditer(content):
        level = len(match.group(1))
        title = match.group(2).strip()
        result['headers'].append(f"{'#' * level} {title}")
    return result


# ─── HTML Analysis ────────────────────────────────────────────────────

_HTML_TAG = re.compile(r'<(head|body|script|style|main|nav|header|footer|section|article|aside)\b')


def analyze_html(content: str) -> dict[str, Any]:
    """Analiza estructura HTML."""
    result: dict[str, Any] = {'tags': []}
    seen: set = set()
    for match in _HTML_TAG.finditer(content):
        tag = match.group(1)
        if tag not in seen:
            seen.add(tag)
            result['tags'].append(tag)
    return result


# ─── CSS Analysis ─────────────────────────────────────────────────────

_CSS_IMPORT = re.compile(r"""@import\s+['"]?([^;'"]+)""")


def analyze_css(content: str) -> dict[str, Any]:
    """Analiza imports CSS."""
    result: dict[str, Any] = {'imports': []}
    for match in _CSS_IMPORT.finditer(content):
        result['imports'].append(match.group(1))
    return result


# ─── Factory ──────────────────────────────────────────────────────────

def analyze_by_ext(ext: str, content: str) -> dict[str, Any]:
    """Analiza contenido según extensión del archivo."""
    if ext in AST_EXTENSIONS:
        return analyze_python(content)
    elif ext in JS_EXTENSIONS:
        return analyze_javascript(content)
    elif ext in ('.md', '.markdown'):
        return analyze_markdown(content)
    elif ext in ('.html', '.htm'):
        return analyze_html(content)
    elif ext in ('.css', '.scss'):
        return analyze_css(content)
    return {}


# ─── Build Summary (from analysis results) ────────────────────────────

# Límites de display
MAX_FUNCTIONS_SHOWN = 10
MAX_CLASSES_SHOWN = 6
MAX_IMPORTS_SHOWN = 12


def build_summary(analysis: dict[str, Any], show_imports: bool = False) -> tuple[str, list[str]]:
    """Construye resumen legible a partir del análisis de un archivo."""
    parts = []
    imports_list = []

    def _fmt_item(item: Any) -> str:
        if isinstance(item, dict):
            name = item.get('name', '?')
            lineno = item.get('lineno')
            end_lineno = item.get('end_lineno')
            if lineno is not None and end_lineno is not None:
                return f"{name}:L{lineno}-L{end_lineno}"
            if lineno is not None:
                return f"{name}:L{lineno}"
            return str(name)
        return str(item)

    if analysis.get('functions'):
        funcs = analysis['functions'][:MAX_FUNCTIONS_SHOWN]
        extra = len(analysis['functions']) - MAX_FUNCTIONS_SHOWN
        s = ', '.join(_fmt_item(f) for f in funcs)
        if extra > 0:
            s += f" (+{extra})"
        parts.append(f"fn: {s}")

    if analysis.get('async_funcs'):
        s = ', '.join(_fmt_item(f) for f in analysis['async_funcs'][:4])
        parts.append(f"async: {s}")

    if analysis.get('classes'):
        cls = analysis['classes'][:MAX_CLASSES_SHOWN]
        extra = len(analysis['classes']) - MAX_CLASSES_SHOWN
        s = ', '.join(_fmt_item(c) for c in cls)
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
