"""analyze_code: analisis profundo de codigo Python con AST.

Sigue el patron Lego: DEFINITION + run().
"""
import ast
import os
from typing import Any

from src.tools._path_helpers import resolve_and_validate_path
from src.tools._analyzers import detect_language, icon
from src.utils.async_utils import run_in_thread
DEFINITION = {
    "type": "function",
    "function": {
        "name": "analyze_code",
        "description": (
            "Analisis profundo de codigo Python con AST. "
            "Muestra funciones con lineas, parametros, llamadas internas, "
            "call graph, imports usados por cada funcion, metricas, "
            "y complejidad ciclomática de cada funcion. "
            "Usa analyze_code con function='nombre' para analizar una funcion especifica. "
            "Opcionalmente detecta duplicados estructurales y referencias cruzadas cross-file. "
            "Sirve para entender rapidamente la estructura y flujo del codigo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo a analizar"
                },
                "function": {
                    "type": "string",
                    "description": "Nombre de funcion/clase especifica para analisis profundo (opcional)",
                    "default": ""
                },
                "find_duplicates": {
                    "type": "boolean",
                    "description": "Si True, busca funciones estructuralmente similares en todo el proyecto (opcional)",
                    "default": False
                },
                "cross_reference": {
                    "type": "boolean",
                    "description": "Si True, muestra que otros archivos llaman a las funciones definidas aca (opcional)",
                    "default": False
                },
                "complexity": {
                    "type": "boolean",
                    "description": "Si True, calcula complejidad ciclomatica de cada funcion y flagge las que exceden umbrales (opcional)",
                    "default": True
                }
            },
            "required": ["path"]
        }
    }
}
MAX_FILE_SIZE = 500 * 1024


# ─── AST Analysis Helpers ─────────────────────────────────────────────

def _get_function_args(node: ast.FunctionDef) -> list[str]:
    """Extrae nombres de parametros de una funcion."""
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
    return args


def _get_function_calls(node: ast.FunctionDef) -> list[dict[str, Any]]:
    """Extrae todas las llamadas a funciones dentro de un nodo."""
    calls = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            if isinstance(sub.func, ast.Name):
                calls.append({"name": sub.func.id, "line": sub.lineno, "type": "direct"})
            elif isinstance(sub.func, ast.Attribute):
                if isinstance(sub.func.value, ast.Name):
                    # obj.method()
                    calls.append({
                        "name": f"{sub.func.value.id}.{sub.func.attr}",
                        "line": sub.lineno,
                        "type": "method",
                    })
                else:
                    calls.append({"name": sub.func.attr, "line": sub.lineno, "type": "method"})
    return calls


def _get_returns(node: ast.FunctionDef) -> list[int]:
    """Encuentra las lineas de return dentro de una funcion."""
    returns = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Return):
            returns.append(sub.lineno)
    return returns


def _get_decorators(node: ast.FunctionDef) -> list[str]:
    """Extrae nombres de decoradores."""
    decs = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            decs.append(dec.id)
        elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
            decs.append(f"{dec.func.id}(...)")
        elif isinstance(dec, ast.Attribute):
            decs.append(dec.attr)
    return decs


def _get_function_body(content_lines: list[str], node: ast.FunctionDef) -> list[dict[str, Any]]:
    """Obtiene una vista comprimida del cuerpo de la funcion."""
    body = []
    for sub in ast.walk(node):
        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue  # skip nested
        if hasattr(sub, 'lineno') and hasattr(sub, 'end_lineno'):
            if sub.lineno != node.lineno:  # skip the def line itself
                kind = type(sub).__name__
                line = sub.lineno
                # Get a snippet of this line
                snippet = content_lines[line - 1].strip() if line <= len(content_lines) else ""
                body.append({"kind": kind, "line": line, "snippet": snippet[:80]})
    return body

def _iter_func_nodes(tree: ast.Module) -> list[tuple[ast.FunctionDef, bool]]:
    """Itera sobre funciones y async functions en el AST."""
    funcs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            funcs.append((node, False))
        elif isinstance(node, ast.AsyncFunctionDef):
            funcs.append((node, True))
    return funcs


def _cyclomatic_complexity(node: ast.AST) -> int:
    """Calcula la complejidad ciclomática de un nodo AST.

    Basado en el estándar McCabe: cada punto de decisión incrementa la complejidad.
    Complejidad base = 1 (el camino lineal).
    +1 por: if, elif, for, while, except, and, or, comprehensions, ternaries.
    """
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While)):
            complexity += 1
        elif isinstance(child, ast.For):
            complexity += 1
        elif isinstance(child, ast.ExceptHandler):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            # Each 'and'/'or' adds a decision point
            complexity += len(child.values) - 1
        elif isinstance(child, ast.ListComp):
            # Each comprehension has an implicit iteration
            complexity += len(child.generators)
        elif isinstance(child, ast.SetComp):
            complexity += len(child.generators)
        elif isinstance(child, ast.DictComp):
            complexity += len(child.generators)
        elif isinstance(child, ast.GeneratorExp):
            complexity += len(child.generators)
        elif isinstance(child, ast.IfExp):
            # Ternary expression: x if cond else y
            complexity += 1
    return complexity


def _complexity_label(cc: int) -> str:
    """Devuelve un label con emoji según la complejidad ciclomática."""
    if cc <= 5:
        return f"🟢 {cc} (baja)"
    elif cc <= 10:
        return f"🟡 {cc} (moderada)"
    elif cc <= 15:
        return f"🟠 {cc} (alta — considerar refactor)"
    else:
        return f"🔴 {cc} (muy alta — refactorizar)"


def _iter_class_nodes(tree: ast.Module) -> list[ast.ClassDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

def _count_lines(node: ast.FunctionDef) -> int:
    return (node.end_lineno or node.lineno) - node.lineno + 1


# ─── Formateo ─────────────────────────────────────────────────────────

# ─── Formateo ─────────────────────────────────────────────────────────

def _format_function_deep(
    node: ast.FunctionDef, is_async: bool, content_lines: list[str],
    call_graph: dict[str, list[dict[str, Any]]],
    all_func_names: set[str],
) -> str:
    """Formatea analisis profundo de una funcion."""
    lines_out = []
    name = node.name
    start = node.lineno
    end = getattr(node, 'end_lineno', start) or start
    line_count = end - start + 1
    prefix = "async " if is_async else ""

    # Cabecera
    lines_out.append(f"\n{'━' * 50}")
    lines_out.append(f"🎯 {prefix}fn {name}  (L:{start}-{end}, {line_count} lines)")

    # Complejidad ciclomática
    cc = _cyclomatic_complexity(node)
    lines_out.append(f"   ├── Ciclomática: {_complexity_label(cc)}")

    # Decoradores
    decs = _get_decorators(node)
    if decs:
        lines_out.append(f"   @{', @'.join(decs)}")

    # Parametros
    args = _get_function_args(node)
    lines_out.append(f"   ├── Parámetros: {', '.join(args) if args else '(ninguno)'}")

    # Returns
    returns = _get_returns(node)
    if returns:
        lines_out.append(f"   ├── Returns en L:{', L:'.join(str(r) for r in returns)}")

    # Cuerpo resumido
    body = _get_function_body(content_lines, node)
    if body:
        # Mostrar lineas clave (assignments, calls, returns, etc.)
        key_lines = [b for b in body if b['kind'] in (
            'Call', 'Return', 'Assign', 'If', 'For', 'While',
            'Try', 'Raise', 'With', 'AsyncFor', 'AsyncWith'
        )]
        if key_lines:
            lines_out.append("   ├── Estructura:")
            for kl in key_lines[:15]:
                lines_out.append(f"   │   L:{kl['line']:<5} {kl['snippet']}")

    # Llamadas
    calls = call_graph.get(name, [])
    if calls:
        internal_calls = [c for c in calls if c['name'].split('.')[0] in all_func_names
                          or c['name'] in all_func_names]
        external_calls = [c for c in calls if c not in internal_calls]

        if internal_calls:
            lines_out.append("   ├── ⚡ Llama a funciones del archivo:")
            for c in internal_calls[:10]:
                lines_out.append(f"   │   ├── {c['name']}() ← L:{c['line']}")
        if external_calls:
            lines_out.append("   ├── 🔗 Llama a externos/builtins:")
            for c in external_calls[:8]:
                lines_out.append(f"   │   ├── {c['name']}() ← L:{c['line']}")

    return '\n'.join(lines_out)


def _format_summary(
    funcs: list[tuple[ast.FunctionDef, bool]],
    classes: list[ast.ClassDef],
    content_lines: list[str],
    call_graph: dict[str, list[dict[str, Any]]],
) -> str:
    """Formatea resumen general del archivo."""
    lines_out = ["\n📊 MÉTRICAS GENERALES"]

    # Totales
    total_lines = len(content_lines)
    n_funcs = len(funcs)
    n_classes = len(classes)

    if funcs:
        avg_lines = sum(_count_lines(f) for f, _ in funcs) // len(funcs)
        longest = max(funcs, key=lambda x: _count_lines(x[0]))
        longest_name = longest[0].name
        longest_lines = _count_lines(longest[0])
        lines_out.append(f"   ├── {total_lines} lines | {n_funcs} funciones | {n_classes} clases")
        lines_out.append(f"   ├── Promedio: ~{avg_lines} lines/funcion")
        lines_out.append(f"   └── Mas larga: {longest_name} ({longest_lines} lines)")
    else:
        lines_out.append(f"   └── {total_lines} lines, sin funciones definidas")

    # Funciones listado
    if funcs:
        lines_out.append("\n📦 FUNCIONES")
        complexity_warnings = []
        for f_node, is_async in sorted(funcs, key=lambda x: x[0].lineno):
            name = f_node.name
            start = f_node.lineno
            end = getattr(f_node, 'end_lineno', start) or start
            lc = end - start + 1
            decs = _get_decorators(f_node)
            args = _get_function_args(f_node)
            prefix = "async " if is_async else ""

            # Cuantas llamadas hace
            calls = call_graph.get(name, [])
            n_calls = len(calls)

            # Complejidad ciclomática
            cc = _cyclomatic_complexity(f_node)
            cc_label = _complexity_label(cc)

            # Linea compacta
            line = f"   ├── {prefix}{name}:L{start}-L{end}"
            line += f"  ({lc} lines, {n_calls} calls, cc={cc})"
            if args:
                line += f"  params: {', '.join(args[:4])}"
                if len(args) > 4:
                    line += " ..."
            if decs:
                line += f"  @{decs[0]}"
            lines_out.append(line)

            # Collect complexity warnings (cc > 10)
            if cc > 10:
                complexity_warnings.append((name, cc, lc))

        # Complexity warnings section
        if complexity_warnings:
            lines_out.append("\n⚠️  COMPLEJIDAD ALTA (cc > 10)")
            for wname, wcc, wlc in sorted(complexity_warnings, key=lambda x: -x[1]):
                lines_out.append(f"   {_complexity_label(wcc)}  {wname} ({wlc} lines)")

    # Clases
    # Clases
    if classes:
        lines_out.append("\n📦 CLASES")
        for cls_node in sorted(classes, key=lambda x: x.lineno):
            name = cls_node.name
            start = cls_node.lineno
            end = getattr(cls_node, 'end_lineno', start) or start
            # Contar metodos adentro
            methods = [n for n in ast.walk(cls_node) if isinstance(n, ast.FunctionDef)]
            lines_out.append(f"   ├── {name}:L{start}-L{end}  ({len(methods)} methods)")

    # Call graph simplificado
    if funcs:
        lines_out.append("\n📈 FLUJO DE LLAMADAS")
        all_names = {f[0].name for f in funcs}
        for f_node, _ in sorted(funcs, key=lambda x: x[0].lineno):
            name = f_node.name
            calls = call_graph.get(name, [])
            internal = [c for c in calls if c['name'] in all_names]
            if internal:
                targets = ' → '.join(c['name'] for c in internal[:5])
                lines_out.append(f"   ├── {name}  →  {targets}")

    return '\n'.join(lines_out)


def _read_and_parse(path: str) -> tuple[list[str], ast.Module | None, str | None]:
    """Lee un archivo y parsea su AST.

    Devuelve (content_lines, tree, error_msg). Si hay error, tree es None.
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            content_lines = content.splitlines(keepends=True)
    except Exception as e:
        return [], None, f"[ERROR] No se pudo leer: {e}"

    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        return content_lines, None, f"[ERROR] Error de sintaxis: {e}"

    return content_lines, tree, None
def _async_audit_report(tree: ast.Module) -> str:
    """Analiza el AST buscando problemas async/sync en el código.
    Detecta: sync def con llamadas async, threading.Lock en async,
    import asyncio en cuerpo, subprocess sin to_thread.
    """
    findings: list[str] = []

    for node in ast.walk(tree):
        # threading.Lock() dentro de async def
        if isinstance(node, ast.AsyncFunctionDef):
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    fn = child.func
                    if isinstance(fn, ast.Attribute) and fn.attr == 'Lock':
                        if isinstance(fn.value, ast.Name) and fn.value.id == 'threading':
                            findings.append(f"   🚨 {node.name}: threading.Lock() en async → bloquea event loop")
                    if isinstance(fn, ast.Attribute) and fn.attr in ('run', 'Popen'):
                        if isinstance(fn.value, ast.Name) and fn.value.id == 'subprocess':
                            findings.append(f"   ⚠️  {node.name}: subprocess.{fn.attr}() async sin to_thread")

        # sync def run() o sync def que llama _repos.xxx.yyy()
        if isinstance(node, ast.FunctionDef) and not isinstance(node, ast.AsyncFunctionDef):
            has_repos_call = False
            has_await_syntax = False
            has_subprocess = False
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    fn = child.func
                    # _repos.algo.metodo() o repos.algo.metodo()
                    if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Attribute):
                        val = fn.value.value if hasattr(fn.value, 'value') else None
                        if hasattr(val, 'id') and val.id in ('_repos', 'repos'):
                            has_repos_call = True
                    # subprocess.run/Popen
                    if isinstance(fn, ast.Attribute) and fn.attr in ('run', 'Popen'):
                        if isinstance(fn.value, ast.Name) and fn.value.id == 'subprocess':
                            has_subprocess = True
                if isinstance(child, ast.Await):
                    has_await_syntax = True
            if has_repos_call and not has_await_syntax:
                findings.append(f"   🚨 {node.name}: sync pero llama repos async → COROUTINE PERDIDA (bug)")
            if has_subprocess:
                findings.append(f"   🛑 {node.name}: subprocess bloqueante → bloquea event loop")

        # import asyncio dentro del cuerpo de función
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.Import):
                    for alias in child.names:
                        if alias.name == 'asyncio':
                            findings.append(f"   ⚠️  {node.name}: import asyncio dentro del cuerpo (mover a top-level)")
                if isinstance(child, ast.ImportFrom) and child.module == 'asyncio':
                    findings.append(f"   ⚠️  {node.name}: from asyncio import ... dentro del cuerpo")

    if not findings:
        return ""

    audit = ["", "⚡ ASYNC AUDIT — posibles problemas async/sync:"]
    audit.extend(findings)
    return "\n".join(audit)


def _build_analysis_output(
    path: str,
    content_lines: list[str],
    tree: ast.Module,
    func_name: str,
    find_dups: bool,
    cross_ref: bool,
) -> str:
    """Construye el output completo del análisis de código."""
    funcs = _iter_func_nodes(tree)
    all_func_names = {f[0].name for f in funcs}
    classes = _iter_class_nodes(tree)

    call_graph: dict[str, list[dict[str, Any]]] = {}
    for f_node, _ in funcs:
        call_graph[f_node.name] = _get_function_calls(f_node)

    imports = [n.names[0].name for n in ast.walk(tree)
               if isinstance(n, (ast.Import, ast.ImportFrom))]

    lang_name, lang_type = detect_language(path)
    lang_icon = icon(lang_type)
    basename = os.path.basename(path)
    output = [f"\n{lang_icon} ANALISIS PROFUNDO: {basename}  ({lang_name})"]
    output.append(f"   Ruta: {path}")
    output.append(f"   Imports: {len(imports)}")

    if func_name:
        found = False
        for f_node, is_async in funcs:
            if f_node.name == func_name:
                output.append(_format_function_deep(
                    f_node, is_async, content_lines, call_graph, all_func_names
                ))
                found = True
                break
        if not found:
            output.append(f"\n[ERROR] Funcion '{func_name}' no encontrada en el archivo.")
            available = sorted(all_func_names)
            if available:
                output.append(f"Funciones disponibles: {', '.join(available[:10])}")
    else:
        output.append(_format_summary(funcs, classes, content_lines, call_graph))

    if find_dups or cross_ref:
        from src.tools._cross_analyzer import context_report as _ctx
        src_root = os.path.dirname(os.path.dirname(path))
        if os.path.isdir(src_root):
            ctx = _ctx(target_path=path, root=src_root,
                       find_duplicates_flag=find_dups, cross_reference_flag=cross_ref)
            if ctx.strip():
                output.append(ctx)

    # ── ASYNC AUDIT (Python only) ────────────────────────────────────
    audit = _async_audit_report(tree)
    if audit:
        output.append(audit)

    result = '\n'.join(output)
    if len(result) > 30000:
        result = result[:30000] + "\n...[truncado]"
    return result


def _sync_analyze(path: str, func_name: str, find_dups: bool, cross_ref: bool) -> str:
    if not os.path.isfile(path):
        return f"[ERROR] El archivo '{path}' no existe."
    size = os.path.getsize(path)
    if size > MAX_FILE_SIZE:
        return f"[ERROR] Archivo demasiado grande ({size / 1024:.0f}KB)."
    lang_name, lang_type = detect_language(path)
    if lang_type != 'snake':
        return f"[INFO] analyze_code solo soporta Python por ahora ({lang_name} detectado). Usa list_files o search_files."
    content_lines, tree, error = _read_and_parse(path)
    if error:
        return error
    return _build_analysis_output(path, content_lines, tree, func_name, find_dups, cross_ref)


async def run(**kwargs: Any) -> str:
    """Punto de entrada principal para analyze_code."""
    path = kwargs.get("path", "").strip()
    func_name = kwargs.get("function", "").strip()
    find_dups = kwargs.get("find_duplicates", False)
    cross_ref = kwargs.get("cross_reference", False)
    if not path:
        return "[ERROR] Proporciona una ruta de archivo."
    path, err = resolve_and_validate_path(path)
    if err:
        return err
    return await run_in_thread(_sync_analyze, path, func_name, find_dups, cross_ref)
