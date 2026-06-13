"""analyze_code: análisis profundo de código con AST, call graph y métricas.

Combina detección de funciones (vía AST), seguimiento de llamadas,
análisis de dependencias y métricas de código en una sola herramienta.
"""
import ast
import logging
import os
from typing import Any

from src.tools._path_helpers import resolve_and_validate_path
from src.tools._analyzers import detect_language, icon

logger = logging.getLogger(__name__)

DEFINITION = {
    "type": "function",
    "function": {
        "name": "analyze_code",
        "description": (
            "Analisis profundo de codigo Python con AST. "
            "Muestra funciones con lineas, parametros, llamadas internas, "
            "call graph, imports usados por cada funcion, y metricas. "
            "Usa analyze_code con function='nombre' para analizar una funcion especifica. "
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


def _count_lines(node: ast.FunctionDef) -> int:
    """Cuenta lineas de una funcion."""
    return (getattr(node, 'end_lineno', node.lineno) or node.lineno) - node.lineno + 1


def _iter_func_nodes(tree: ast.Module) -> list[tuple[ast.FunctionDef, bool]]:
    """Itera sobre funciones y async functions en el AST."""
    funcs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            funcs.append((node, False))
        elif isinstance(node, ast.AsyncFunctionDef):
            funcs.append((node, True))
    return funcs


def _iter_class_nodes(tree: ast.Module) -> list[ast.ClassDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]


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
            lines_out.append(f"   ├── Estructura:")
            for kl in key_lines[:15]:
                lines_out.append(f"   │   L:{kl['line']:<5} {kl['snippet']}")

    # Llamadas
    calls = call_graph.get(name, [])
    if calls:
        internal_calls = [c for c in calls if c['name'].split('.')[0] in all_func_names
                          or c['name'] in all_func_names]
        external_calls = [c for c in calls if c not in internal_calls]

        if internal_calls:
            lines_out.append(f"   ├── ⚡ Llama a funciones del archivo:")
            for c in internal_calls[:10]:
                lines_out.append(f"   │   ├── {c['name']}() ← L:{c['line']}")
        if external_calls:
            lines_out.append(f"   ├── 🔗 Llama a externos/builtins:")
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
    lines_out = [f"\n📊 MÉTRICAS GENERALES"]

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
        lines_out.append(f"\n📦 FUNCIONES")
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

            # Linea compacta
            line = f"   ├── {prefix}{name}:L{start}-L{end}"
            line += f"  ({lc} lines, {n_calls} calls)"
            if args:
                line += f"  params: {', '.join(args[:4])}"
                if len(args) > 4:
                    line += " ..."
            if decs:
                line += f"  @{decs[0]}"
            lines_out.append(line)

    # Clases
    if classes:
        lines_out.append(f"\n📦 CLASES")
        for cls_node in sorted(classes, key=lambda x: x.lineno):
            name = cls_node.name
            start = cls_node.lineno
            end = getattr(cls_node, 'end_lineno', start) or start
            # Contar metodos adentro
            methods = [n for n in ast.walk(cls_node) if isinstance(n, ast.FunctionDef)]
            lines_out.append(f"   ├── {name}:L{start}-L{end}  ({len(methods)} methods)")

    # Call graph simplificado
    if funcs:
        lines_out.append(f"\n📈 FLUJO DE LLAMADAS")
        all_names = {f[0].name for f in funcs}
        for f_node, _ in sorted(funcs, key=lambda x: x[0].lineno):
            name = f_node.name
            calls = call_graph.get(name, [])
            internal = [c for c in calls if c['name'] in all_names]
            if internal:
                targets = ' → '.join(c['name'] for c in internal[:5])
                lines_out.append(f"   ├── {name}  →  {targets}")

    return '\n'.join(lines_out)


# ─── Run ──────────────────────────────────────────────────────────────

def run(**kwargs: Any) -> str:
    path = kwargs.get("path", "").strip()
    func_name = kwargs.get("function", "").strip()

    if not path:
        return "[ERROR] Proporciona una ruta de archivo."

    path, err = resolve_and_validate_path(path)
    if err:
        return err

    if not os.path.isfile(path):
        return f"[ERROR] El archivo '{path}' no existe."

    size = os.path.getsize(path)
    if size > MAX_FILE_SIZE:
        return f"[ERROR] Archivo demasiado grande ({size / 1024:.0f}KB)."

    # Solo analisis Python por ahora (con AST)
    lang_name, lang_type = detect_language(path)
    if lang_type != 'snake':
        return f"[INFO] analyze_code solo soporta Python por ahora ({lang_name} detectado). Usa list_files o search_files."

    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            content_lines = content.splitlines(keepends=True)
    except Exception as e:
        return f"[ERROR] No se pudo leer: {e}"

    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        return f"[ERROR] Error de sintaxis: {e}"

    # Extraer funciones y call graph
    funcs = _iter_func_nodes(tree)
    all_func_names = {f[0].name for f in funcs}
    classes = _iter_class_nodes(tree)

    # Build call graph
    call_graph: dict[str, list[dict[str, Any]]] = {}
    for f_node, _ in funcs:
        call_graph[f_node.name] = _get_function_calls(f_node)

    imports = [n.names[0].name for n in ast.walk(tree)
               if isinstance(n, (ast.Import, ast.ImportFrom))]

    # Encabezado
    lang_icon = icon(lang_type)
    basename = os.path.basename(path)
    output = [f"\n{lang_icon} ANALISIS PROFUNDO: {basename}  ({lang_name})"]
    output.append(f"   Ruta: {path}")
    output.append(f"   Imports: {len(imports)}")

    if func_name:
        # Analisis de una funcion especifica
        found = False
        for f_node, is_async in funcs:
            if f_node.name == func_name:
                result = _format_function_deep(
                    f_node, is_async, content_lines, call_graph, all_func_names
                )
                output.append(result)
                found = True
                break
        if not found:
            output.append(f"\n[ERROR] Funcion '{func_name}' no encontrada en el archivo.")
            # Sugerir funciones disponibles
            available = sorted(all_func_names)
            if available:
                output.append(f"Funciones disponibles: {', '.join(available[:10])}")
    else:
        # Resumen general del archivo
        output.append(_format_summary(funcs, classes, content_lines, call_graph))

    result = '\n'.join(output)

    if len(result) > 30000:
        result = result[:30000] + "\n...[truncado]"

    return result
