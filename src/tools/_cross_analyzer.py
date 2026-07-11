"""_cross_analyzer: análisis cross-file de duplicados y referencias.

Módulo Lego independiente — no depende de tools ni de core.
Solo importa AST estándar de Python.

Uso:
    from src.tools._cross_analyzer import analyze_duplicates, cross_reference, context_report
"""
import ast
import os
from collections import defaultdict
from typing import Any

# ─── FINGERPRINTING ───────────────────────────────────────────────────

def _fingerprint(node: ast.AST) -> tuple | None:
    """Crea una huella estructural de una función.

    La huella ignora nombres de variables y valores literales,
    detectando solo: cantidad de parámetros, tipos de statements en el cuerpo.
    Dos funciones con misma huella son ESTRUCTURALMENTE similares.
    """
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        sig = f"def({len(node.args.args)},{len(node.body)})"
        body_types = tuple(type(stmt).__name__ for stmt in node.body)
        return (sig, body_types)
    return None


# ─── ESCANEO ──────────────────────────────────────────────────────────

def _iter_py_files(root: str) -> list[str]:
    """Itera archivos .py recursivamente, excluyendo __init__ y tests."""
    results = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if not fn.endswith('.py'):
                continue
            if fn.startswith('__') and fn != '__init__.py' and fn != '__main__.py':
                continue
            fpath = os.path.join(dirpath, fn)
            results.append(fpath)
    return sorted(results)


def _extract_functions(tree: ast.AST, rel_path: str) -> list[dict[str, Any]]:
    """Extrae todas las funciones de un AST con metadata."""
    funcs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append({
                "name": node.name,
                "lineno": node.lineno,
                "file": rel_path,
                "node": node,
            })
    return funcs


# ─── ANÁLISIS DE DUPLICADOS ──────────────────────────────────────────

def analyze_duplicates(
    root: str = "",
    ignore_fns: set[str] | None = None,
    ignore_patterns: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Busca funciones con estructura similar en todo el proyecto.

    Args:
        root: Directorio raíz a escanear. Si es vacío, usa 'src/'.
        ignore_fns: Nombres de función a ignorar (ej: {'run', '__init__'}).
        ignore_patterns: Patrones en nombres a ignorar (ej: {'_migration_'}).

    Returns:
        Lista de grupos duplicados. Cada grupo tiene 'fingerprint', 'count',
        'functions' (lista de {name, file, lineno}).
    """
    if not root:
        root = os.path.join(os.path.dirname(__file__), "..")

    if ignore_fns is None:
        ignore_fns = {"run", "__init__"}
    if ignore_patterns is None:
        ignore_patterns = {"_migration_"}

    fingerprints: dict[tuple, list[dict[str, Any]]] = defaultdict(list)

    for fpath in _iter_py_files(root):
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                tree = ast.parse(f.read())
        except (SyntaxError, Exception):
            continue

        rel = os.path.relpath(fpath, root) if os.path.commonpath([root, fpath]) else fpath
        for func in _extract_functions(tree, rel):
            name = func["name"]
            # Aplicar filtros
            if name in ignore_fns:
                continue
            if any(p in name for p in ignore_patterns):
                continue

            fp = _fingerprint(func["node"])
            if fp:
                fingerprints[fp].append({
                    "name": name,
                    "file": rel,
                    "lineno": func["lineno"],
                })

    # Armar resultado: solo fingerprints con múltiples funciones en diferentes archivos
    result = []
    seen_sets: set[tuple] = set()

    for fp, funcs in sorted(fingerprints.items(), key=lambda x: -len(x[1])):
        if len(funcs) < 2:
            continue
        # Verificar que no sean todas del mismo archivo
        unique_files = set(f["file"] for f in funcs)
        if len(unique_files) < 2:
            continue

        # Evitar reportar el mismo grupo duplicado
        names = tuple(sorted(f["name"] for f in funcs))
        if names in seen_sets:
            continue
        seen_sets.add(names)

        result.append({
            "fingerprint": f"def({fp[0]}) con {fp[1][:5]}...",
            "count": len(funcs),
            "functions": funcs,
        })

    return result


# ─── REFERENCIAS CRUZADAS ─────────────────────────────────────────────

def cross_reference(
    target_file: str,
    root: str = "",
) -> list[dict[str, Any]]:
    """Busca qué otros archivos llaman a funciones definidas en target_file.

    Args:
        target_file: Ruta del archivo a analizar.
        root: Directorio raíz del proyecto.

    Returns:
        Lista de {function, called_by: [{file, lineno}]}
    """
    if not root:
        root = os.path.dirname(os.path.abspath(target_file))
        # Subir hasta encontrar src/ o web/
        for _ in range(4):
            parent = os.path.dirname(root)
            if os.path.basename(parent) in ("src", "web", "K-Chat"):
                root = parent
                break
            root = parent

    # 1. Extraer funciones definidas en target_file
    try:
        with open(target_file, "r", encoding="utf-8", errors="replace") as f:
            tree = ast.parse(f.read())
    except (SyntaxError, Exception):
        return []

    defined_funcs: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined_funcs[node.name] = node.lineno

    # 2. Buscar llamadas a esas funciones en todo el proyecto
    calls: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for fpath in _iter_py_files(root):
        if os.path.samefile(fpath, target_file):
            continue
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                tree2 = ast.parse(f.read())
        except (SyntaxError, Exception):
            continue

        rel = os.path.relpath(fpath, root) if os.path.commonpath([root, fpath]) else fpath
        for node in ast.walk(tree2):
            if isinstance(node, ast.Call):
                fn = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if fn and fn in defined_funcs:
                    calls[fn].append({
                        "file": rel,
                        "lineno": node.lineno,
                    })

    # Armar resultado
    result = []
    for fn_name, callers in sorted(calls.items(), key=lambda x: -len(x[1])):
        if callers:
            result.append({
                "function": fn_name,
                "defined_at": defined_funcs[fn_name],
                "called_by": callers,
            })

    return result


# ─── FILTROS DE FALSOS POSITIVOS ──────────────────────────────────────

DEFAULT_IGNORE_FUNCTIONS: set[str] = {
    "run", "__init__", "__getitem__", "__getattr__",
    "provider_name", "supports_streaming", "supports_tools",
    "supports_reasoning", "list_models", "chat", "chat_stream",
}

DEFAULT_IGNORE_PATTERNS: set[str] = {
    "_migration_", "_migration_", "_test_", "test_",
}


def filter_duplicates(
    duplicates: list[dict[str, Any]],
    ignore_fns: set[str] | None = None,
    ignore_patterns: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Filtra falsos positivos de analyze_duplicates()."""
    if ignore_fns is None:
        ignore_fns = DEFAULT_IGNORE_FUNCTIONS
    if ignore_patterns is None:
        ignore_patterns = DEFAULT_IGNORE_PATTERNS

    filtered = []
    for group in duplicates:
        # Filtrar funciones dentro del grupo que matchean patrones de exclusión
        funcs = [f for f in group["functions"]
                 if f["name"] not in ignore_fns
                 and not any(p in f["name"] for p in ignore_patterns)]

        if len(funcs) >= 2:
            unique_files = set(f["file"] for f in funcs)
            if len(unique_files) >= 2:
                filtered.append({
                    **group,
                    "functions": funcs,
                    "count": len(funcs),
                })

    return filtered


# ─── REPORTE LEGIBLE ──────────────────────────────────────────────────

def context_report(
    path: str = "",
    find_duplicates: bool = False,
    cross_reference_flag: bool = False,
) -> str:
    """Genera un reporte de contexto legible para el asistente.

    Args:
        path: Ruta del archivo a analizar (para cross_reference).
        find_duplicates: Si True, busca duplicados estructurales.
        cross_reference_flag: Si True, busca referencias cruzadas desde path.

    Returns:
        Texto formateado para mostrar al usuario.
    """
    lines: list[str] = []

    if find_duplicates:
        dups = analyze_duplicates()
        filtered = filter_duplicates(dups)

        if filtered:
            lines.append("📋 POSIBLES DUPLICADOS ESTRUCTURALES:")
            for group in filtered[:10]:  # Top 10
                files_summary = ", ".join(
                    f"{f['name']}() en {f['file']}:{f['lineno']}"
                    for f in group["functions"][:3]
                )
                extra = f" (+{group['count'] - 3} mas)" if group["count"] > 3 else ""
                lines.append(f"  🔷 {group['fingerprint']}")
                lines.append(f"     {files_summary}{extra}")
        else:
            lines.append("📋 NO se encontraron duplicados estructurales significativos.")

    if cross_reference_flag and path:
        refs = cross_reference(path)
        if refs:
            if find_duplicates:
                lines.append("")
            lines.append("📞 REFERENCIAS CRUZADAS (quien llama a estas funciones):")
            for ref in refs[:10]:
                callers_summary = ", ".join(
                    f"{c['file']}:{c['lineno']}" for c in ref["called_by"][:3]
                )
                extra = f" (+{len(ref['called_by']) - 3} mas)" if len(ref["called_by"]) > 3 else ""
                lines.append(f"  📞 {ref['function']}() (definida en linea {ref['defined_at']})")
                lines.append(f"     Llamada desde: {callers_summary}{extra}")
        else:
            if find_duplicates:
                lines.append("")
            lines.append("📞 No se encontraron referencias cruzadas externas.")

    return "\n".join(lines)
