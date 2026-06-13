"""_validators: validación de sintaxis cross-language (Python, JS, HTML, CSS, JSON, YAML).

Compartido entre tools (edit_file, write_file). Reduce duplicación de lógica.
"""
import json
import logging
import os
import re
import subprocess
import tempfile
import sys
from typing import Any

logger = logging.getLogger(__name__)


def validate_python(content: str, path: str = "<unknown>") -> dict[str, Any]:
    """Valida sintaxis Python con compile()."""
    try:
        compile(content, path, 'exec')
        return {"status": "ok", "message": "Sintaxis Python OK"}
    except SyntaxError as e:
        return {
            "status": "error",
            "message": f"Error de sintaxis: {e.msg}",
            "line": e.lineno,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def validate_json(content: str, path: str = "<unknown>") -> dict[str, Any]:
    """Valida sintaxis JSON."""
    try:
        json.loads(content)
        return {"status": "ok", "message": "JSON valido"}
    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "message": f"JSON invalido: {e.msg}",
            "line": e.lineno,
        }


def validate_javascript(content: str, path: str = "<unknown>") -> dict[str, Any]:
    """Valida sintaxis JS/TS con Node.js si está disponible."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
            tmp.write(content)
            tmp.flush()
            tmp_path = tmp.name

        result = subprocess.run(
            ["node", "--check", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return {"status": "ok", "message": "Sintaxis JS/TS OK"}
        else:
            # Parsear error de Node
            err = result.stderr.strip()
            line = None
            m = re.search(r"(\w+Error): (.+)", err)
            msg = m.group(0) if m else err
            m2 = re.search(r":(\d+):", err)
            line = int(m2.group(1)) if m2 else None
            return {"status": "error", "message": msg, "line": line}
    except FileNotFoundError:
        return {"status": "skipped", "message": "Node.js no disponible para validar JS/TS"}
    except subprocess.TimeoutExpired:
        return {"status": "skipped", "message": "Timeout validando JS/TS"}
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass


def validate_html(content: str, path: str = "<unknown>") -> dict[str, Any]:
    """Valida estructura HTML básica."""
    # Verificar etiquetas básicas de cierre
    # No es un parser completo, pero detecta errores comunes
    stack = []
    # Encontrar tags HTML (simplificado)
    tags = re.finditer(r'<(/?)(\w+)[^>]*>', content)
    errors = []
    for m in tags:
        closing = m.group(1)
        tag = m.group(2).lower()
        if tag in ('br', 'hr', 'img', 'input', 'meta', 'link', '!doctype'):
            continue  # self-closing
        if closing:
            if stack and stack[-1] == tag:
                stack.pop()
            else:
                expected = stack[-1] if stack else "?"
                errors.append(f"Tag de cierre </{tag}> inesperado (se esperaba </{expected}>)")
        else:
            stack.append(tag)

    if not errors and not stack:
        return {"status": "ok", "message": "Estructura HTML OK"}
    elif errors:
        return {"status": "error", "message": "; ".join(errors[:3])}
    else:
        unclosed = ", ".join(f"<{t}>" for t in stack[:5])
        return {"status": "warning", "message": f"Tags sin cerrar: {unclosed}"}


def validate_css(content: str, path: str = "<unknown>") -> dict[str, Any]:
    """Valida estructura CSS básica."""
    # Verificar llaves balanceadas
    opens = content.count('{')
    closes = content.count('}')
    if opens == closes:
        return {"status": "ok", "message": "Estructura CSS OK"}
    elif opens > closes:
        return {"status": "error", "message": f"Llaves sin cerrar: {opens - closes} abiertas de mas"}
    else:
        return {"status": "error", "message": f"Llaves de mas: {closes - opens} cierres extras"}


def validate_yaml(content: str, path: str = "<unknown>") -> dict[str, Any]:
    """Valida sintaxis YAML si PyYAML está disponible."""
    try:
        import yaml
        yaml.safe_load(content)
        return {"status": "ok", "message": "YAML valido"}
    except ImportError:
        return {"status": "skipped", "message": "PyYAML no instalado"}
    except Exception as e:
        return {"status": "error", "message": f"YAML invalido: {e}"}


def validate_toml(content: str, path: str = "<unknown>") -> dict[str, Any]:
    """Valida sintaxis TOML si tomllib/toml está disponible."""
    if sys.version_info >= (3, 11):
        import tomllib
        try:
            tomllib.loads(content)
            return {"status": "ok", "message": "TOML valido"}
        except Exception as e:
            return {"status": "error", "message": f"TOML invalido: {e}"}
    else:
        return {"status": "skipped", "message": "TOML no soportado (Python 3.11+)"}


# Mapa de validadores por extensión
_VALIDATORS: dict[str, Any] = {
    '.py': validate_python,
    '.pyi': validate_python,
    '.json': validate_json,
    '.js': validate_javascript,
    '.jsx': validate_javascript,
    '.ts': validate_javascript,
    '.tsx': validate_javascript,
    '.mjs': validate_javascript,
    '.html': validate_html,
    '.htm': validate_html,
    '.css': validate_css,
    '.scss': validate_css,
    '.yaml': validate_yaml,
    '.yml': validate_yaml,
    '.toml': validate_toml,
    '.cfg': None,
    '.ini': None,
    '.md': None,
    '.txt': None,
}


def validate_file(filepath: str, content: str | None = None) -> dict[str, Any]:
    """Valida sintaxis de un archivo según su extensión.

    Args:
        filepath: Ruta del archivo (se usa la extensión para determinar el validador)
        content: Contenido del archivo (si es None, se lee del disco)

    Returns:
        dict con status: "ok" | "error" | "warning" | "skipped"
    """
    if content is None:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except Exception as e:
            return {"status": "error", "message": f"No se pudo leer: {e}"}

    ext = os.path.splitext(filepath)[1].lower()
    validator = _VALIDATORS.get(ext)

    if validator is None:
        return {"status": "skipped", "message": f"Sin validador para {ext}"}

    return validator(content, filepath)
