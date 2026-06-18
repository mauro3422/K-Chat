"""dependency_graph: analiza dependencias entre modulos Python.

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
from src.utils.async_utils import run_in_thread

from src.tools._arch_checker import check_file, Violation, Rule, DEFAULT_RULES


DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "dependency_graph",
        "description": (
            "Grafo de dependencias entre módulos Python. "
            "Recorre un directorio, extrae imports de cada archivo, y muestra "
            "un mapa completo de qué importa qué, clasificado como "
            "downward (correcto), same-layer, upward (potencial violación), "
            "o banned (violación arquitectónica). "
            "Opcionalmente puede enfocarse en un solo archivo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directorio raíz a analizar (ej: 'src/')"
                },
                "file": {
                    "type": "string",
                    "description": "Archivo específico a analizar (opcional). Si se provee, solo muestra dependencias de ese archivo.",
                    "default": ""
                },
                "verbose": {
                    "type": "boolean",
                    "description": "Si True, muestra imports under TYPE_CHECKING separados (default: False)",
                    "default": False
                }
            },
            "required": ["path"]
        }
    }
}


# ─── Import extraction (AST-based) ────────────────────────────────────

def _extract_imports(file_path: str) -> list[dict[str, Any]]:
    """Extract imports from a Python file with TYPE_CHECKING detection."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return []

    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return []

    # Find TYPE_CHECKING blocks
    type_checking_ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
                end = getattr(node, 'end_lineno', node.lineno) or node.lineno
                type_checking_ranges.append((node.lineno, end))

    def _in_type_checking(lineno: int) -> bool:
        return any(start <= lineno <= end for start, end in type_checking_ranges)

    results: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append({
                    "module": alias.name,
                    "names": [alias.name],
                    "line": node.lineno,
                    "type_checking": _in_type_checking(node.lineno),
                })
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = [a.name for a in node.names]
            results.append({
                "module": module,
                "names": names,
                "line": node.lineno,
                "type_checking": _in_type_checking(node.lineno),
            })

    return results


# ─── Project root detection ───────────────────────────────────────────

def _find_project_root(start_path: str) -> str:
    """Detect project root by looking for src/ and web/ directories."""
    p = Path(start_path).resolve()
    for parent in [p] + list(p.parents):
        if (parent / "src").is_dir() and (parent / "web").is_dir():
            return str(parent)
    # Fallback: parent of src/
    for parent in [p] + list(p.parents):
        if parent.name == "src":
            return str(parent.parent)
    return str(p.parent)


# ─── Layer classification ─────────────────────────────────────────────

# Layer hierarchy (lower number = lower layer)
_LAYER_MAP: dict[str, int] = {
    "src/memory": 0,
    "src/llm": 1,
    "src/tools": 2,
    "src/context": 3,
    "src/core": 4,
    "src/skills": 2,
    "src/api": 5,
    "web": 6,
    "channels": 6,
}


def _classify_import(
    source_rel: str,
    target_module: str,
    project_root: str,
) -> dict[str, Any]:
    """Classify an import as downward/same/upward/banned.

    Returns dict with keys: direction, target_file, reason.
    """
    # Determine source layer
    source_layer = None
    for prefix, layer_num in sorted(_LAYER_MAP.items(), key=lambda x: -len(x[0])):
        if source_rel.startswith(prefix) or source_rel.replace(os.sep, "/").startswith(prefix):
            source_layer = (prefix, layer_num)
            break

    if source_layer is None:
        return {"direction": "external", "target_file": None, "reason": "not in src/"}

    # Resolve target module to a file
    # Convert module path to file path
    target_parts = target_module.split(".")
    target_file = None

    # Try to find the target file
    for i in range(len(target_parts), 0, -1):
        candidate = os.path.join(project_root, *target_parts[:i])
        if os.path.isfile(candidate + ".py"):
            target_file = candidate + ".py"
            break
        if os.path.isdir(candidate) and os.path.isfile(os.path.join(candidate, "__init__.py")):
            target_file = os.path.join(candidate, "__init__.py")
            break

    if target_file is None:
        return {"direction": "external", "target_file": None, "reason": "target not found locally"}

    # Determine target layer
    target_rel = os.path.relpath(target_file, project_root).replace(os.sep, "/")
    target_layer = None
    for prefix, layer_num in sorted(_LAYER_MAP.items(), key=lambda x: -len(x[0])):
        if target_rel.startswith(prefix):
            target_layer = (prefix, layer_num)
            break

    if target_layer is None:
        return {"direction": "external", "target_file": target_rel, "reason": "target not in known layers"}

    # Compare layers
    src_num = source_layer[1]
    tgt_num = target_layer[1]

    if tgt_num > src_num:
        return {"direction": "upward", "target_file": target_rel, "reason": f"{source_layer[0]} → {target_layer[0]} (upward coupling)"}
    elif tgt_num < src_num:
        return {"direction": "downward", "target_file": target_rel, "reason": f"{source_layer[0]} → {target_layer[0]} (correct)"}
    else:
        return {"direction": "same", "target_file": target_rel, "reason": f"same layer ({source_layer[0]})"}


# ─── Main logic ───────────────────────────────────────────────────────

def _analyze_file(
    file_path: str,
    project_root: str,
    verbose: bool = False,
) -> dict[str, Any]:
    """Analyze dependencies for a single file."""
    abs_path = os.path.abspath(file_path)
    rel_path = os.path.relpath(abs_path, project_root).replace(os.sep, "/")

    imports = _extract_imports(abs_path)

    deps: list[dict[str, Any]] = []
    for imp in imports:
        # Skip TYPE_CHECKING unless verbose
        if imp["type_checking"] and not verbose:
            continue

        # Only process local imports (from src.* or similar)
        module = imp["module"]
        if not module.startswith(("src.", "channels.", "web.", "dependencies.")):
            continue

        classification = _classify_import(rel_path, module, project_root)
        deps.append({
            "module": module,
            "names": imp["names"],
            "line": imp["line"],
            "type_checking": imp["type_checking"],
            **classification,
        })

    # Check for violations
    violations = check_file(abs_path, project_root=project_root)

    return {
        "file": rel_path,
        "dependencies": deps,
        "violations": violations,
    }


def _sync_dependency_graph(path: str, target_file: str, verbose: bool) -> str:
    resolved, err = resolve_and_validate_path(path)
    if err:
        return err
    if not os.path.isdir(resolved):
        return f"[ERROR] '{path}' no es un directorio."
    project_root = _find_project_root(resolved)
    all_files = []
    for root, dirs, files in os.walk(resolved):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules", ".git", "venv", ".venv")]
        for fname in sorted(files):
            if fname.endswith(".py"):
                all_files.append(os.path.join(root, fname))
    if not all_files:
        return f"[INFO] No se encontraron archivos .py en {path}"
    if target_file:
        matched = [f for f in all_files if target_file in f]
        if not matched:
            return f"[ERROR] No se encontró '{target_file}' en {path}"
        all_files = matched
    results = []
    all_violations = []
    direction_counts = defaultdict(int)
    for fp in all_files:
        result = _analyze_file(fp, project_root, verbose=verbose)
        results.append(result)
        all_violations.extend(result["violations"])
        for dep in result["dependencies"]:
            direction_counts[dep["direction"]] += 1
    total_deps = sum(direction_counts.values())
    lines = [f"\n📊 DEPENDENCY GRAPH — {path} ({len(results)} archivos, {total_deps} dependencias)\n"]
    for result in results:
        deps = result["dependencies"]
        violations = result["violations"]
        fname = result["file"]
        if not deps and not violations:
            continue
        lines.append(f"📄 {fname}")
        for dep in deps:
            icon = {"downward": "✅", "same": "🔹", "upward": "⚠️", "banned": "🚫", "external": "📦"}.get(dep["direction"], "❓")
            tc_note = " (TYPE_CHECKING)" if dep["type_checking"] else ""
            target = dep.get("target_file") or dep["module"]
            names_str = ", ".join(dep["names"][:3])
            if len(dep["names"]) > 3:
                names_str += f" (+{len(dep['names'])-3})"
            lines.append(f"   {icon} → {target}  ({names_str}){tc_note}")
        if violations:
            for v in violations:
                lines.append(f"   🚫 {v}")
        lines.append("")
    lines.append("📈 RESUMEN DE DIRECCIONES:")
    for direction, count in sorted(direction_counts.items(), key=lambda x: -x[1]):
        icon = {"downward": "✅", "same": "🔹", "upward": "⚠️", "banned": "🚫", "external": "📦"}.get(direction, "❓")
        lines.append(f"   {icon} {direction}: {count}")
    if all_violations:
        lines.append(f"\n🔴 VIOLACIONES: {len(all_violations)}")
        for v in all_violations:
            lines.append(f"   {v}")
    else:
        lines.append(f"\n🟢 Sin violaciones arquitectónicas")
    dep_pairs = set()
    for result in results:
        src = result["file"]
        for dep in result["dependencies"]:
            tgt = dep.get("target_file", "")
            if tgt:
                dep_pairs.add((src, tgt))
    cycles = []
    seen = set()
    for src, tgt in dep_pairs:
        if (tgt, src) in dep_pairs and src != tgt:
            pair = tuple(sorted([src, tgt]))
            if pair in seen:
                continue
            seen.add(pair)
            src_dir = os.path.dirname(src)
            tgt_dir = os.path.dirname(tgt)
            if src_dir == tgt_dir:
                continue
            cycles.append((src, tgt))
    if cycles:
        lines.append(f"\n🔄 CICLOS DETECTADOS: {len(cycles)}")
        for src, tgt in cycles[:5]:
            lines.append(f"   {src} ↔ {tgt}")
    result_str = "\n".join(lines)
    if len(result_str) > 30000:
        result_str = result_str[:30000] + "\n...[truncado]"
    return result_str


async def run(**kwargs: Any) -> str:
    path = kwargs.get("path", "").strip()
    target_file = kwargs.get("file", "").strip()
    verbose = kwargs.get("verbose", False)
    if not path:
        return "[ERROR] Proporciona un path (ej: 'src/')"
    return await run_in_thread(_sync_dependency_graph, path, target_file, verbose)
