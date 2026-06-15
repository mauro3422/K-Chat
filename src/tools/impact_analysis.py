"""impact_analysis: analiza el impacto de cambiar una funcion o clase.

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


DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "impact_analysis",
        "description": (
            "Analiza el impacto de cambiar una función o clase. "
            "Dado un nombre y archivo, encuentra todos los llamadores "
            "directos e indirectos, y estima qué archivos se romperían."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nombre de la función o clase a analizar"
                },
                "path": {
                    "type": "string",
                    "description": "Archivo donde está definida la función/clase"
                },
                "include_internal": {
                    "type": "boolean",
                    "description": "Si True, incluye llamadores dentro del mismo archivo (default: False)",
                    "default": False
                }
            },
            "required": ["name", "path"]
        }
    }
}


def _find_project_root(start_path: str) -> str:
    """Detect project root."""
    p = Path(start_path).resolve()
    for parent in [p] + list(p.parents):
        if (parent / "src").is_dir() and (parent / "web").is_dir():
            return str(parent)
    return str(p.parent)


def _find_callers(
    name: str,
    project_root: str,
    exclude_file: str,
    include_internal: bool = False,
) -> list[dict[str, Any]]:
    """Find all files that reference or call a given function/class name."""
    callers: list[dict[str, Any]] = []
    exclude_abs = os.path.abspath(exclude_file)

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules", ".git", "venv", ".venv")]

        for fname in sorted(files):
            if not fname.endswith(".py"):
                continue

            fpath = os.path.join(root, fname)
            fpath_abs = os.path.abspath(fpath)

            # Skip self unless include_internal
            if fpath_abs == exclude_abs and not include_internal:
                continue

            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                continue

            # Quick text check first
            if name not in content:
                continue

            try:
                tree = ast.parse(content, filename=fpath)
            except SyntaxError:
                continue

            rel_path = os.path.relpath(fpath, project_root)
            references: list[dict[str, Any]] = []

            for node in ast.walk(tree):
                # from X import name
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name == name or (alias.asname and alias.asname == name):
                            references.append({
                                "line": node.lineno,
                                "type": "import",
                                "detail": f"from {node.module} import {alias.name}",
                            })

                # import name
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == name or (alias.asname and alias.asname == name):
                            references.append({
                                "line": node.lineno,
                                "type": "import",
                                "detail": f"import {alias.name}",
                            })

                # Direct call: name(...)
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == name:
                        references.append({
                            "line": node.lineno,
                            "type": "call",
                            "detail": f"{name}(...)",
                        })
                    elif isinstance(node.func, ast.Attribute) and node.func.attr == name:
                        references.append({
                            "line": node.lineno,
                            "type": "method_call",
                            "detail": f"...{name}(...)",
                        })

                # Attribute access: name.attr
                elif isinstance(node, ast.Attribute):
                    if isinstance(node.value, ast.Name) and node.value.id == name:
                        references.append({
                            "line": node.lineno,
                            "type": "attribute",
                            "detail": f"{name}.{node.attr}",
                        })

                # Name usage (general): name
                elif isinstance(node, ast.Name) and node.id == name:
                    # Skip if it's a function definition (that's the source, not a caller)
                    if not isinstance(node, ast.FunctionDef):
                        references.append({
                            "line": node.lineno,
                            "type": "usage",
                            "detail": name,
                        })

            if references:
                callers.append({
                    "file": rel_path,
                    "references": references,
                })

    return callers


def _get_function_signature(file_path: str, name: str) -> str | None:
    """Extract the function/class signature from the file."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        tree = ast.parse(content, filename=file_path)
    except (SyntaxError, Exception):
        return None

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            # Extract args
            args = []
            for arg in node.args.args:
                args.append(arg.arg)
            if node.args.vararg:
                args.append(f"*{node.args.vararg.arg}")
            if node.args.kwonlyargs:
                for arg in node.args.kwonlyargs:
                    args.append(arg.arg)
            if node.args.kwarg:
                args.append(f"**{node.args.kwarg.arg}")

            prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            return f"{prefix}def {name}({', '.join(args)})"

        elif isinstance(node, ast.ClassDef) and node.name == name:
            methods = [n.name for n in ast.iter_child_nodes(node)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            return f"class {name} ({len(methods)} methods: {', '.join(methods[:5])})"

    return None


def _sync_impact(name: str, path: str, include_internal: bool) -> str:
    resolved, err = resolve_and_validate_path(path)
    if err:
        return err
    if not os.path.isfile(resolved):
        return f"[ERROR] '{path}' no es un archivo."
    project_root = _find_project_root(resolved)
    rel_path = os.path.relpath(resolved, project_root)
    signature = _get_function_signature(resolved, name)
    callers = _find_callers(name, project_root, resolved, include_internal=include_internal)
    lines = [f"\n🎯 IMPACT ANALYSIS — {name} @ {rel_path}\n"]
    if signature:
        lines.append(f"📌 Firma actual:")
        lines.append(f"   {signature}")
        lines.append("")
    if not callers:
        lines.append("✅ Sin dependencias externas — cambio seguro.")
    else:
        total_refs = sum(len(c["references"]) for c in callers)
        lines.append(f"📊 {len(callers)} archivo(s) dependen de '{name}' ({total_refs} referencias):\n")
        for caller in callers:
            fname = caller["file"]
            refs = caller["references"]
            imports = [r for r in refs if r["type"] == "import"]
            calls = [r for r in refs if r["type"] in ("call", "method_call")]
            attrs = [r for r in refs if r["type"] == "attribute"]
            usages = [r for r in refs if r["type"] == "usage"]
            lines.append(f"📄 {fname}")
            if imports:
                for r in imports:
                    lines.append(f"   📦 L:{r['line']}  {r['detail']}")
            if calls:
                for r in calls:
                    lines.append(f"   🔴 L:{r['line']}  {r['detail']}")
            if attrs:
                for r in attrs:
                    lines.append(f"   ⚠️  L:{r['line']}  {r['detail']}")
            if usages:
                for r in usages:
                    lines.append(f"   🔹 L:{r['line']}  {r['detail']}")
            lines.append("")
        if calls:
            lines.append("🔴 RIESGO: Cambios en la firma romperían:")
            for caller in callers:
                call_refs = [r for r in caller["references"] if r["type"] in ("call", "method_call")]
                if call_refs:
                    lines.append(f"   → {caller['file']} ({len(call_refs)} llamadas)")
        elif imports:
            lines.append("🟡 RIESGO BAJO: Solo se importa, no se llama directamente.")
    result_str = "\n".join(lines)
    if len(result_str) > 30000:
        result_str = result_str[:30000] + "\n...[truncado]"
    return result_str


async def run(**kwargs: Any) -> str:
    name = kwargs.get("name", "").strip()
    path = kwargs.get("path", "").strip()
    include_internal = kwargs.get("include_internal", False)
    if not name:
        return "[ERROR] Proporciona el nombre de la función o clase a analizar."
    if not path:
        return "[ERROR] Proporciona el path del archivo donde está definida."
    return await asyncio.to_thread(_sync_impact, name, path, include_internal)
    if err:
        return err

    if not os.path.isfile(resolved):
        return f"[ERROR] '{path}' no es un archivo."

    project_root = _find_project_root(resolved)
    rel_path = os.path.relpath(resolved, project_root)

    # Get current signature
    signature = _get_function_signature(resolved, name)

    # Find all callers
    callers = _find_callers(name, project_root, resolved, include_internal=include_internal)

    # Build output
    lines = [f"\n🎯 IMPACT ANALYSIS — {name} @ {rel_path}\n"]

    if signature:
        lines.append(f"📌 Firma actual:")
        lines.append(f"   {signature}")
        lines.append("")

    if not callers:
        lines.append("✅ Sin dependencias externas — cambio seguro.")
    else:
        total_refs = sum(len(c["references"]) for c in callers)
        lines.append(f"📊 {len(callers)} archivo(s) dependen de '{name}' ({total_refs} referencias):\n")

        for caller in callers:
            fname = caller["file"]
            refs = caller["references"]

            # Categorize references
            imports = [r for r in refs if r["type"] == "import"]
            calls = [r for r in refs if r["type"] in ("call", "method_call")]
            attrs = [r for r in refs if r["type"] == "attribute"]
            usages = [r for r in refs if r["type"] == "usage"]

            lines.append(f"📄 {fname}")

            if imports:
                for r in imports:
                    lines.append(f"   📦 L:{r['line']}  {r['detail']}")
            if calls:
                for r in calls:
                    lines.append(f"   🔴 L:{r['line']}  {r['detail']}")
            if attrs:
                for r in attrs:
                    lines.append(f"   ⚠️  L:{r['line']}  {r['detail']}")
            if usages:
                for r in usages:
                    lines.append(f"   🔹 L:{r['line']}  {r['detail']}")

            lines.append("")

        # Risk assessment
        if calls:
            lines.append("🔴 RIESGO: Cambios en la firma romperían:")
            for caller in callers:
                call_refs = [r for r in caller["references"] if r["type"] in ("call", "method_call")]
                if call_refs:
                    lines.append(f"   → {caller['file']} ({len(call_refs)} llamadas)")
        elif imports:
            lines.append("🟡 RIESGO BAJO: Solo se importa, no se llama directamente.")

    result_str = "\n".join(lines)
    if len(result_str) > 30000:
        result_str = result_str[:30000] + "\n...[truncado]"
    return result_str
