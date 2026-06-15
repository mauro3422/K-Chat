"""audit_tools: audita la async-readiness de todas las tools del sistema.

Analiza cada tool en src/tools/ y reporta:
  - Sync vs Async (def run)
  - subprocess bloqueante sin to_thread
  - threading.Lock dentro de async
  - imports dentro del cuerpo de la función
  - llamadas a repos async desde función sync
  - file I/O directo (open/read/write) sin to_thread
"""

import ast
import os
import logging
import asyncio
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TOOLS_DIR = Path(__file__).parent.resolve()

# ── Helpers de análisis con AST ─────────────────────────────────────


def _get_tool_files() -> list[Path]:
    """Devuelve todos los .py en src/tools/ excluyendo helpers privados (_*)."""
    files = sorted(TOOLS_DIR.glob("*.py"))
    return [f for f in files if not f.name.startswith("_")]


def _parse_source(path: Path) -> ast.Module | None:
    try:
        source = path.read_text(encoding="utf-8")
        return ast.parse(source)
    except SyntaxError as e:
        logger.warning("Syntax error in %s: %s", path.name, e)
        return None
    except Exception as e:
        logger.warning("Error reading %s: %s", path.name, e)
        return None


def _find_run_function(tree: ast.Module) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Encuentra la función `run` en el módulo."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run":
            return node
    return None


def _has_subprocess(node: ast.AST) -> bool:
    """Busca subprocess.run o subprocess.Popen en el AST."""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            # subprocess.run(...)
            if isinstance(func, ast.Attribute) and func.attr == "run":
                if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
                    return True
            # subprocess.Popen(...)
            if isinstance(func, ast.Attribute) and func.attr == "Popen":
                if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
                    return True
            # asyncio.create_subprocess_exec or asyncio.create_subprocess_shell
            if isinstance(func, ast.Attribute) and func.attr in ("create_subprocess_exec", "create_subprocess_shell"):
                return True
    return False


def _has_threading_lock(node: ast.AST) -> bool:
    """Busca threading.Lock() en el AST."""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Attribute) and func.attr == "Lock":
                if isinstance(func.value, ast.Name) and func.value.id == "threading":
                    return True
                # threading.Lock puede ser importado como `from threading import Lock`
                if isinstance(func.value, ast.Name) and func.value.id == "Lock":
                    return True
    return False


def _has_import_asyncio_in_body(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Busca `import asyncio` dentro del cuerpo de la función."""
    for child in ast.walk(func):
        if isinstance(child, ast.Import):
            for alias in child.names:
                if alias.name == "asyncio":
                    return True
        # from asyncio import ...
        if isinstance(child, ast.ImportFrom):
            if child.module == "asyncio":
                return True
    return False


def _has_blocking_file_io(node: ast.AST) -> list[str]:
    """Busca open() o .read()/.write() directo sin to_thread en el cuerpo."""
    findings: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            # open(...) directo
            if isinstance(func, ast.Name) and func.id == "open":
                findings.append("open() directo sin to_thread")
            # file.write(...) o file.read(...)
            if isinstance(func, ast.Attribute) and func.attr in ("write", "read", "readlines", "readline"):
                # Check if it's direct file I/O (not to_thread)
                # We'll flag .read()/.write() calls as potential blocking I/O
                # but filter out common patterns
                parent_expr = _find_parent_call(child, node, "to_thread")
                if not parent_expr:
                    findings.append(f".{func.attr}() potencialmente bloqueante sin to_thread")
    return list(set(findings))  # dedup


def _find_parent_call(target: ast.AST, root: ast.AST, func_name: str) -> bool:
    """Chequea si target está envuelto en una llamada a `func_name(...)`."""
    for parent in ast.walk(root):
        if isinstance(parent, ast.Call):
            if isinstance(parent.func, ast.Name) and parent.func.id == func_name:
                # Check if target is an argument of this call
                if any(arg is target for arg in parent.args):
                    return True
            if isinstance(parent.func, ast.Attribute) and parent.func.attr == func_name:
                if any(arg is target for arg in parent.args):
                    return True
    return False


def _calls_async_repos_from_sync(func: ast.FunctionDef) -> bool:
    """Busca llamadas a _repos.{algo}.{metodo}() en una función sync."""
    for child in ast.walk(func):
        if isinstance(child, ast.Call):
            # Recursivamente buscar _repos.xxx.yyy()
            func_chain = child.func
            if isinstance(func_chain, ast.Attribute) and \
               isinstance(func_chain.value, ast.Attribute) and \
               isinstance(func_chain.value.value, ast.Name) and \
               func_chain.value.value.id == "_repos":
                return True
            # También session_repo, tool_calls, etc.
            if isinstance(func_chain, ast.Attribute):
                val = func_chain.value
                if isinstance(val, ast.Attribute) and isinstance(val.value, ast.Name):
                    if val.value.id in ("_repos", "repos"):
                        return True
    return False


# ── Análisis principal ─────────────────────────────────────────────


def _analyze_tool(filepath: Path) -> dict[str, Any]:
    """Analiza un tool file y devuelve un report de async readiness."""
    result: dict[str, Any] = {
        "file": filepath.name,
        "status": "ok",
        "issues": [],
        "warnings": [],
    }

    tree = _parse_source(filepath)
    if tree is None:
        result["status"] = "error"
        result["issues"].append("No se pudo parsear el archivo")
        return result

    run_fn = _find_run_function(tree)
    if run_fn is None:
        result["status"] = "warning"
        result["warnings"].append("No tiene función run()")
        return result

    is_async = isinstance(run_fn, ast.AsyncFunctionDef)

    if is_async:
        result["type"] = "async"
        # Check threading.Lock inside async
        if _has_threading_lock(run_fn):
            result["issues"].append("🚨 threading.Lock() DENTRO de async → bloquea event loop")

        # Check blocking file I/O
        io_issues = _has_blocking_file_io(run_fn)
        if io_issues:
            result["issues"].append(f"🚨 I/O bloqueante sin to_thread: {', '.join(io_issues)}")

        # Check import asyncio in body
        if _has_import_asyncio_in_body(run_fn):
            result["warnings"].append("⚠️ import asyncio dentro del cuerpo (mover a top-level)")

        # Check subprocess
        if _has_subprocess(run_fn):
            result["warnings"].append("⚠️ subprocess.run() en async (necesita to_thread o create_subprocess)")

    else:
        result["type"] = "sync"
        result["issues"].append("🚨 sync def run() → bloquea event loop en asyncio.gather()")

        # Check subprocess (most dangerous)
        if _has_subprocess(run_fn):
            result["issues"].append("   🛑 subprocess.run() bloqueante (máximo riesgo)")

        # Check blocking file I/O
        io_issues = _has_blocking_file_io(run_fn)
        if io_issues:
            result["warnings"].append(f"   ⚠️ I/O directo: {', '.join(io_issues)}")

        # Check calls to async repos
        if _calls_async_repos_from_sync(run_fn):
            result["issues"].append("   🚨 llama a repos async sin await → COROUTINE PERDIDA (BUG)")

    return result


def _sync_audit(verbose: bool) -> str:
    """Sync: analiza todas las tools y arma reporte. Corre en to_thread."""
    files = _get_tool_files()
    if not files:
        return "[ERROR] No se encontraron tool files."
    results: list[dict[str, Any]] = []
    for fp in files:
        results.append(_analyze_tool(fp))
    lines = [f"\n🔍 AUDITORÍA DE TOOLS — {len(results)} tools analizadas\n"]
    async_count = sum(1 for r in results if r.get("type") == "async")
    sync_count = sum(1 for r in results if r.get("type") == "sync")
    error_count = sum(1 for r in results if r["status"] == "error")
    issues_total = sum(len(r["issues"]) for r in results)
    lines.append(f"📊 RESUMEN:")
    lines.append(f"   ✅ Async def run(): {async_count}")
    lines.append(f"   ❌ Sync def run(): {sync_count}  ← BLOQUEAN EVENT LOOP")
    lines.append(f"   🚨 Issues totales: {issues_total}")
    if error_count:
        lines.append(f"   ⚠️  Errores de parseo: {error_count}")
    lines.append("")
    has_issues = any(r["issues"] for r in results) or any(r["warnings"] for r in results)
    if not has_issues:
        lines.append("🎉 Todas las tools están correctas en async-readiness!\n")
    for r in results:
        if not r["issues"] and not r["warnings"] and not verbose:
            continue
        icon = "✅" if not r["issues"] else "❌"
        ttype = r.get("type", "?")
        lines.append(f"{icon} {r['file']} ({ttype})")
        for issue in r["issues"]:
            lines.append(f"   {issue}")
        for warn in r["warnings"]:
            lines.append(f"   {warn}")
        if not r["issues"] and not r["warnings"] and verbose:
            lines.append("   ✅ Sin issues")
        lines.append("")
    lines.append("── RECOMENDACIONES ──")
    lines.append("1) Convertir sync → async para todas las tools con I/O")
    lines.append("2) Usar asyncio.to_thread() para file I/O y subprocess en async")
    lines.append("3) Reemplazar threading.Lock por asyncio.Lock en async")
    lines.append("4) Mover import asyncio a top-level")
    lines.append("5) Si todas son async, eliminar inspect.iscoroutine() en runner.py")
    lines.append("")
    result_str = "\n".join(lines)
    if len(result_str) > 30000:
        result_str = result_str[:30000] + "\n...[truncado]"
    return result_str


async def run(**kwargs: Any) -> str:
    """Audita todas las tools y reporta async-readiness."""
    verbose = kwargs.get("verbose", False)
    return await asyncio.to_thread(_sync_audit, verbose)


DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "audit_tools",
        "description": (
            "Audita la async-readiness de todas las tools del sistema. "
            "Escanea cada tool en src/tools/ y reporta sync/async, subprocess sin to_thread, "
            "threading.Lock en async, imports en el cuerpo, y repos async llamados desde sync."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "verbose": {
                    "type": "boolean",
                    "description": "Mostrar incluso tools sin issues",
                    "default": False,
                }
            },
        },
    },
}
