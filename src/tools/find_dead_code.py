"""find_dead_code: detecta codigo no referenciado en el proyecto.

Sigue el patron Lego: DEFINITION + run().
"""
import ast
import logging
import os
import re
import asyncio
from collections import defaultdict
from typing import Any
from pathlib import Path

from src.tools._path_helpers import resolve_and_validate_path

logger = logging.getLogger(__name__)

from src.tools._path_helpers import resolve_and_validate_path


DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "find_dead_code",
        "description": (
            "Detecta código no referenciado. "
            "Busca funciones, clases, y exports que están definidos pero "
            "nadie importa fuera de su propio archivo. "
            "También puede detectar imports no utilizados en un archivo. "
            "Modo quick: solo text search sin AST, mucho más rápido para directorios grandes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta de archivo o directorio a analizar"
                },
                "dead_imports": {
                    "type": "boolean",
                    "description": "Si True, también detecta imports no utilizados en el archivo (default: True)",
                    "default": True
                },
                "exclude_tests": {
                    "type": "boolean",
                    "description": "Si True, excluye archivos de tests del análisis (default: True)",
                    "default": True
                },
                "quick": {
                    "type": "boolean",
                    "description": "Modo rápido: solo text search sin AST para directorios grandes. Más rápido pero menos preciso (default: False)",
                    "default": False
                }
            },
            "required": ["path"]
        }
    }
}
DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "find_dead_code",
        "description": (
            "Detecta código no referenciado. "
            "Busca funciones, clases, y exports que están definidos pero "
            "nadie importa fuera de su propio archivo. "
            "También puede detectar imports no utilizados en un archivo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta de archivo o directorio a analizar"
                },
                "dead_imports": {
                    "type": "boolean",
                    "description": "Si True, también detecta imports no utilizados en el archivo (default: True)",
                    "default": True
                },
                "exclude_tests": {
                    "type": "boolean",
                    "description": "Si True, excluye archivos de tests del análisis (default: True)",
                    "default": True
                }
            },
            "required": ["path"]
        }
    }
}


# ─── AST helpers ──────────────────────────────────────────────────────

def _extract_top_level_definitions(file_path: str) -> dict[str, dict[str, Any]]:
    """Extract top-level functions, classes, and module-level assignments."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return {}

    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return {}

    definitions: dict[str, dict[str, Any]] = {}

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            definitions[node.name] = {
                "type": "function",
                "line": node.lineno,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
            }
        elif isinstance(node, ast.ClassDef):
            methods = [n.name for n in ast.iter_child_nodes(node)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            definitions[node.name] = {
                "type": "class",
                "line": node.lineno,
                "methods": methods,
            }
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    definitions[target.id] = {
                        "type": "variable",
                        "line": node.lineno,
                    }

    return definitions


def _check_name_used(name: str, tree: ast.Module, import_line: int) -> bool:
    """Check if a name (from an import) is used anywhere in the AST beyond the import line."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name and node.lineno != import_line:
            return True
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == name:
                return True
    return False


# ─── Reverse index (optimization) ─────────────────────────────────────

def _build_name_index(project_root: str) -> dict[str, set[str]]:
    """Build a reverse index: name → set of files that reference it.

    Single pass over all files, then lookups are O(1).
    """
    index: dict[str, set[str]] = defaultdict(set)

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules", ".git", "venv", ".venv")]

        for fname in files:
            if not fname.endswith(".py"):
                continue

            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, project_root)

            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    tree = ast.parse(f.read(), filename=fpath)
            except (SyntaxError, Exception):
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    index[node.id].add(rel_path)
                elif isinstance(node, ast.Attribute):
                    if isinstance(node.value, ast.Name):
                        index[node.value.id].add(rel_path)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        index[alias.name].add(rel_path)
                        if alias.asname:
                            index[alias.asname].add(rel_path)
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        index[alias.name].add(rel_path)
                        if alias.asname:
                            index[alias.asname].add(rel_path)

    return index


# ─── Main analysis ────────────────────────────────────────────────────

def _analyze_file(
    file_path: str,
    project_root: str,
    name_index: dict[str, set[str]],
    dead_imports: bool = True,
) -> dict[str, Any]:
    """Analyze a single file for dead code using pre-built index."""
    abs_path = os.path.abspath(file_path)
    rel_path = os.path.relpath(abs_path, project_root)

    definitions = _extract_top_level_definitions(abs_path)

    # Get AST for unused import detection
    unused_imports: list[dict[str, Any]] = []
    if dead_imports:
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            tree = ast.parse(content, filename=abs_path)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.asname or alias.name.split(".")[0]
                        # Check if this name is used anywhere in the file (other than import)
                        if not _check_name_used(name, tree, node.lineno):
                            unused_imports.append({
                                "name": name,
                                "line": node.lineno,
                                "context": f"import {alias.name}",
                            })
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        name = alias.asname or alias.name
                        if not _check_name_used(name, tree, node.lineno):
                            unused_imports.append({
                                "name": name,
                                "line": node.lineno,
                                "context": f"from {node.module} import {alias.name}",
                            })
        except (SyntaxError, Exception):
            pass

    # Check references for each definition using the index
    dead: list[dict[str, Any]] = []
    for def_name, def_info in definitions.items():
        # Skip dunder methods
        if def_name.startswith("__") and def_name.endswith("__"):
            continue

        referencing_files = name_index.get(def_name, set())
        # Remove self-references
        referencing_files = {f for f in referencing_files if f != rel_path}

        if not referencing_files:
            dead.append({
                "name": def_name,
                "type": def_info["type"],
                "line": def_info["line"],
                "references": [],
            })

    return {
        "file": rel_path,
        "definitions": definitions,
        "dead_code": dead,
        "unused_imports": unused_imports,
    }


def _quick_search(project_root: str, name: str, exclude_file: str) -> bool:
    """Fast text search for a name across all Python files. No AST parsing."""
    exclude_abs = os.path.abspath(exclude_file)
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules", ".git", "venv", ".venv")]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            if os.path.abspath(fpath) == exclude_abs:
                continue
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if name in content:
                    return True
            except Exception:
                continue
    return False


def _sync_find_dead_code(path: str, dead_imports: bool, exclude_tests: bool, quick: bool) -> str:
    resolved, err = resolve_and_validate_path(path)
    if err:
        return err
    project_root = None
    p = Path(resolved).resolve()
    for parent in [p] + list(p.parents):
        if (parent / "src").is_dir() and (parent / "web").is_dir():
            project_root = str(parent)
            break
    if project_root is None:
        project_root = str(Path(resolved).parent.parent)
    if os.path.isfile(resolved):
        files = [resolved]
    elif os.path.isdir(resolved):
        files = []
        for root, dirs, fnames in os.walk(resolved):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules", ".git", "venv", ".venv")]
            for fname in sorted(fnames):
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                if exclude_tests and "test" in fname.lower():
                    continue
                files.append(fpath)
    else:
        return f"[ERROR] '{path}' no es un archivo ni directorio válido."
    if not files:
        return f"[INFO] No se encontraron archivos .py en {path}"
    name_index = None
    if not quick:
        name_index = _build_name_index(project_root)
    results = []
    total_dead = 0
    total_unused_imports = 0
    for fp in files:
        if quick:
            definitions = _extract_top_level_definitions(fp)
            dead = []
            unused_imports = []
            for def_name, def_info in definitions.items():
                if def_name.startswith("__") and def_name.endswith("__"):
                    continue
                if not _quick_search(project_root, def_name, fp):
                    dead.append({"name": def_name, "type": def_info["type"], "line": def_info["line"], "references": []})
            rel_path = os.path.relpath(os.path.abspath(fp), project_root)
            results.append({"file": rel_path, "definitions": definitions, "dead_code": dead, "unused_imports": unused_imports})
        else:
            result = _analyze_file(fp, project_root, name_index, dead_imports=dead_imports)
            results.append(result)
        total_dead += len(results[-1]["dead_code"])
        total_unused_imports += len(results[-1]["unused_imports"])
    lines = [f"\n🔍 DEAD CODE ANALYSIS — {path} ({len(results)} archivos)\n"]
    has_issues = False
    for result in results:
        dead = result["dead_code"]
        unused = result["unused_imports"]
        if not dead and not unused:
            continue
        has_issues = True
        lines.append(f"📄 {result['file']}")
        for d in dead:
            lines.append(f"   ❌ {d['type']} {d['name']}:L{d['line']} (0 referencias en el proyecto)")
        for u in unused:
            lines.append(f"   ⚠️  unused import '{u['name']}' (L:{u['line']}) — {u['context']}")
        lines.append("")
    if not has_issues:
        lines.append("✅ No se encontró código muerto ni imports no utilizados.")
    lines.append(f"\n📈 RESUMEN:")
    lines.append(f"   📁 Archivos analizados: {len(results)}")
    lines.append(f"   💀 Funciones/clases sin referencias: {total_dead}")
    lines.append(f"   ⚠️  Imports no utilizados: {total_unused_imports}")
    result_str = "\n".join(lines)
    if len(result_str) > 30000:
        result_str = result_str[:30000] + "\n...[truncado]"
    return result_str


async def run(**kwargs: Any) -> str:
    path = kwargs.get("path", "").strip()
    dead_imports = kwargs.get("dead_imports", True)
    exclude_tests = kwargs.get("exclude_tests", True)
    quick = kwargs.get("quick", False)
    if not path:
        return "[ERROR] Proporciona una ruta (archivo o directorio)."
    return await asyncio.to_thread(_sync_find_dead_code, path, dead_imports, exclude_tests, quick)
