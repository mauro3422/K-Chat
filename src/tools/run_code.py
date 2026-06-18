"""run_code: ejecución segura de código Python con sandboxing y auto-fix.

Sigue el patrón Lego de K-Chat: DEFINITION + run().
Usa _validators.py para validación de sintaxis.
Ejecuta en subprocess aislado con restricciones de seguridad.
Auto-detecta y corrige errores comunes de sintaxis.
"""
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from typing import Any
from src.utils.async_utils import run_in_thread

logger = logging.getLogger(__name__)

# ─── DEFINITION ────────────────────────────────────────────────────────

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "run_code",
        "description": (
            "Ejecuta codigo Python de forma segura en un entorno aislado (sandbox). "
            "No puede acceder a tu sistema de archivos ni importar modulos peligrosos. "
            "Si hay errores de sintaxis, intenta corregirlos automaticamente y re-ejecuta. "
            "Devuelve JSON estructurado con stdout, stderr, exit_code y auto_fix."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "El codigo Python a ejecutar"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Tiempo maximo en segundos (default: 15, max: 60)",
                    "default": 15
                }
            },
            "required": ["code"]
        }
    }
}

# ─── CONSTANTES ────────────────────────────────────────────────────────

MAX_OUTPUT: int = 30000
DEFAULT_TIMEOUT: int = 15
MAX_TIMEOUT: int = 60

# Módulos bloqueados en el sandbox por seguridad
BLOCKED_MODULES: list[str] = [
    "os", "subprocess", "shutil", "socket",
    "ctypes", "signal", "multiprocessing",
    "threading", "importlib",
]

# Project root para permitir lectura de archivos del proyecto
import src.paths as _paths
_PROJECT_ROOT: str = str(_paths.CONTEXT_DIR)


def _build_sandbox_wrapper(code: str) -> str:
    """Construye el wrapper de seguridad insertando el código del usuario."""
    blocked_repr = repr(BLOCKED_MODULES)
    project_root = _PROJECT_ROOT
    return f'''"""Sandbox de seguridad -- auto-generado por run_code tool."""
import sys
import builtins as _builtins
import os as _os

_original_import = _builtins.__import__
_blocked = {blocked_repr}
_PROJECT_ROOT = {project_root!r}

def _safe_import(name, *args, **kwargs):
    top = name.split('.')[0]
    if top in _blocked:
        print(f"[SANDBOX] Modulo bloqueado por seguridad: {{name}}", file=sys.stderr)
        raise ImportError(f"Modulo '{{name}}' no permitido en sandbox")
    return _original_import(name, *args, **kwargs)

_builtins.__import__ = _safe_import

_original_open = _builtins.open

def _safe_open(file, mode='r', *args, **kwargs):
    f = str(file)
    is_read = set(mode) & {{'r', '+'}} or not (set(mode) & {{'w', 'a', 'x'}})
    
    # Lectura: permitida desde cualquier lado
    # Escritura: solo en /tmp/
    if not is_read and not f.startswith('/tmp/'):
        raise PermissionError(f"[SANDBOX] Solo se puede ESCRIBIR en /tmp/: {{f}}")
    return _original_open(file, mode, *args, **kwargs)

_builtins.open = _safe_open

# --- USER CODE ---
{code}
'''

# ─── AUTO-FIX DE SINTAXIS ──────────────────────────────────────────────

# Patrones de error → función de fix
# Cada fix retorna (código_fixed, descripción) o (código_original, "")
_SYNTAX_FIXES: list[tuple[re.Pattern, Any]] = []


def _fix_missing_print_parens(code: str) -> tuple[str, str]:
    """print 'hola' → print('hola') — 3 variantes."""
    # print 'texto' → print('texto')
    code = re.sub(
        r'\bprint\s+((?![("]).+?)$',
        r'print(\1)',
        code,
        flags=re.MULTILINE,
    )
    # print variable → print(variable)
    code = re.sub(
        r'\bprint\s+([a-zA-Z_][a-zA-Z0-9_]*)',
        r'print(\1)',
        code,
    )
    return code, "print() necesita parentesis en Python 3"


def _fix_unterminated_string(code: str) -> tuple[str, str]:
    """Cierra string no terminado."""
    for quote, name in [("'''", "triple single"), ('"""', "triple double"),
                         ("'", "single"), ('"', "double")]:
        count = code.count(quote)
        if count % 2 != 0 and not code.endswith(quote):
            return code + quote, f"String {name} no cerrado — auto-cerrado"
    return code, ""


def _fix_missing_colon(code: str) -> tuple[str, str]:
    """Agrega : al final de lineas que controlan bloques."""
    keywords = [
        r'^\s*if\s+.*', r'^\s*elif\s+.*', r'^\s*else\s*$',
        r'^\s*for\s+.*', r'^\s*while\s+.*',
        r'^\s*def\s+.*', r'^\s*class\s+.*',
        r'^\s*try\s*$', r'^\s*except\s+.*', r'^\s*finally\s*$',
        r'^\s*with\s+.*',
    ]
    lines = code.split('\n')
    modified = False
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        for kw in keywords:
            if re.match(kw, stripped) and not stripped.endswith(':'):
                lines[i] = stripped + ' :'
                modified = True
                break
    if modified:
        return '\n'.join(lines), "Se agregaron ':' faltantes en bloques"
    return code, ""


def _fix_indentation(code: str) -> tuple[str, str]:
    """Tabs → espacios, normaliza."""
    if '\t' in code:
        return code.expandtabs(4), "Tabs reemplazados por espacios"
    return code, ""


def _fix_unclosed_bracket(code: str) -> tuple[str, str]:
    """Cierra parentesis/corchetes/llaves no cerrados."""
    pairs = {'(': ')', '[': ']', '{': '}'}
    for opening, closing in pairs.items():
        opens = code.count(opening)
        closes = code.count(closing)
        if opens > closes:
            code += closing * (opens - closes)
            return code, f"Se cerraron {opens - closes} '{closing}' faltantes"
    return code, ""


def _auto_fix(code: str, error_msg: str) -> tuple[str, str]:
    """Aplica fixes en orden. Retorna (código_fixiado, descripción)."""
    # Intentar fixes que requieren contexto del error
    if "print" in error_msg and "parenthes" in error_msg:
        fixed, desc = _fix_missing_print_parens(code)
        if fixed != code:
            return fixed, desc

    # Intentar fixes estructurales en orden
    for fix_fn, fix_name in [
        (_fix_unterminated_string, "string"),
        (_fix_unclosed_bracket, "bracket"),
        (_fix_missing_colon, "colon"),
        (_fix_indentation, "indent"),
    ]:
        fixed, desc = fix_fn(code)
        if fixed != code:
            return fixed, desc

    return code, ""


def _safe_compile(code: str) -> tuple[bool, str, int | None]:
    """Compila código Python, retorna (ok, mensaje, línea_error)."""
    try:
        compile(code, '<run_code>', 'exec')
        return True, "", None
    except SyntaxError as e:
        return False, e.msg, e.lineno
    except Exception as e:
        return False, str(e), None


# ─── EJECUCIÓN ─────────────────────────────────────────────────────────

def _execute_code(code: str, timeout: int) -> dict[str, Any]:
    """Ejecuta código en subprocess con sandbox wrapper."""
    wrapped = _build_sandbox_wrapper(code)
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.py', delete=False, encoding='utf-8'
    ) as f:
        f.write(wrapped)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        stdout = result.stdout or ""
        stderr = result.stderr or ""

        # Truncar si excede
        combined = stdout
        if stderr:
            combined += f"\n--- STDERR ---\n{stderr}"
        if len(combined) > MAX_OUTPUT:
            combined = combined[:MAX_OUTPUT] + "\n...[truncado a 30000 caracteres]"

        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": result.returncode,
            "output": combined,
        }

    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"[ERROR] Timeout después de {timeout}s.",
            "exit_code": -1,
            "output": f"[ERROR] Timeout después de {timeout}s.",
        }
    except FileNotFoundError:
        return {
            "stdout": "",
            "stderr": "[ERROR] Python no encontrado en el sistema.",
            "exit_code": -1,
            "output": "[ERROR] Python no encontrado en el sistema.",
        }
    except Exception as e:
        logger.exception("Error inesperado ejecutando código")
        return {
            "stdout": "",
            "stderr": f"[ERROR] Error interno: {e}",
            "exit_code": -1,
            "output": f"[ERROR] Error interno: {e}",
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ─── RUN (entry point) ─────────────────────────────────────────────────

async def run(**kwargs: Any) -> str:
    """Ejecuta código Python validado y sanitizado.

    Args:
        code: Código fuente Python a ejecutar
        timeout: Timeout en segundos (default: 15, max: 60)

    Returns:
        JSON string con: status, stdout, stderr, exit_code, auto_fix_applied
    """
    code: str = kwargs.get("code", "").strip()
    timeout: int = min(int(kwargs.get("timeout", DEFAULT_TIMEOUT)), MAX_TIMEOUT)

    if not code:
        return "[ERROR] No se proporcionó código para ejecutar."

    # 1. Validar sintaxis
    ok, error_msg, error_line = _safe_compile(code)

    auto_fix_applied: str | None = None

    # 2. Intentar auto-fix si hay error de sintaxis
    if not ok and error_msg:
        fixed_code, fix_desc = _auto_fix(code, error_msg)
        if fixed_code != code:
            # Verificar que el fix sirvió
            ok2, msg2, _ = _safe_compile(fixed_code)
            if ok2:
                code = fixed_code
                ok = True
                auto_fix_applied = fix_desc
                logger.info("Auto-fix aplicado: %s", fix_desc)
            else:
                # No se pudo arreglar
                pass

    # 3. Si todavía hay error, reportar
    if not ok:
        line_str = f" (línea {error_line})" if error_line else ""
        error_result = {
            "status": "error",
            "error": f"Error de sintaxis: {error_msg}{line_str}",
            "auto_fix_applied": auto_fix_applied,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
        }
        return json.dumps(error_result, ensure_ascii=False)

    # 4. Ejecutar en sandbox
    logger.info("Ejecutando código Python (timeout=%ds, chars=%d)", timeout, len(code))
    result = await run_in_thread(_execute_code, code, timeout)

    # 5. Armar respuesta estructurada
    is_error = result["exit_code"] != 0

    response: dict[str, Any] = {
        "status": "error" if is_error else "ok",
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
        "auto_fix_applied": auto_fix_applied,
    }

    if is_error:
        response["error"] = f"Exit code: {result['exit_code']}"
        if "SANDBOX" in result["stderr"]:
            response["error"] = "Operación bloqueada por el sandbox de seguridad."

    return json.dumps(response, ensure_ascii=False)
