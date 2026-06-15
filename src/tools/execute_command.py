import logging
import os
import subprocess
import asyncio
from typing import Any

from src.tools._path_helpers import resolve_and_validate_path
logger = logging.getLogger(__name__)

DEFINITION = {
    "type": "function",
    "function": {
        "name": "execute_command",
        "description": (
            "Ejecuta un comando en tu terminal Linux. "
            "Usalo para correr scripts, compilar codigo, mover archivos, "
            "instalar paquetes, buscar archivos con grep, etc. "
            "Soporta operadores de shell (&&, |, >, etc.) y funciona en Linux y Windows. "
            "El working directory default es ~/proyectos. "
            "El output se trunca a 30000 caracteres."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "El comando a ejecutar (ej: 'ls -la', 'cd src && python3 script.py', 'dir', 'echo hola')"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Tiempo maximo en segundos (default: 30, max: 120)",
                    "default": 30
                },
                "cwd": {
                    "type": "string",
                    "description": "Directorio de trabajo (default: ~/proyectos, '~' = home del usuario)",
                    "default": "~/proyectos"
                }
            },
            "required": ["command"]
        }
    }
}

MAX_OUTPUT = 30000
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120

DANGEROUS_PATTERNS = [
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=", "format",
    ":(){ :|:& };:", "> /dev/sda", "chmod -R 000 /",
]


def _is_dangerous(cmd: str) -> tuple[bool, str]:
    cmd_lower = cmd.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            return True, (
                f"Comando bloqueado por seguridad: contiene '{pattern}'. "
                "Si realmente queres ejecutarlo, ejecutalo manualmente."
            )
    return False, ""


async def run(**kwargs: Any) -> str:
    command = kwargs.get("command", "").strip()
    timeout = min(int(kwargs.get("timeout", DEFAULT_TIMEOUT)), MAX_TIMEOUT)
    cwd = kwargs.get("cwd", "~/proyectos")

    if not command:
        return "[ERROR] No command provided."

    resolved_cwd, err = resolve_and_validate_path(cwd)
    if err:
        return err

    # Validar que el directorio exista
    if not os.path.isdir(resolved_cwd):
        return (
            f"[ERROR] El directorio '{cwd}' no existe. "
            f"Asegurate de que la carpeta exista o pasa un cwd valido."
        )

    # Check de seguridad
    dangerous, msg = _is_dangerous(command)
    if dangerous:
        return f"[ERROR] {msg}"

    logger.info("Executing (shell mode): %s (cwd=%s, timeout=%ds)", command[:200], cwd, timeout)

    try:
        result = await asyncio.to_thread(
            subprocess.run, command,
            shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=resolved_cwd,
        )

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n--- STDERR ---\n{result.stderr}"
        if result.returncode != 0:
            output = f"[EXIT CODE: {result.returncode}]\n{output}"

        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + "\n...[truncado a 30000 caracteres]"

        return output if output else "(sin output)"

    except subprocess.TimeoutExpired:
        logger.warning("Command timed out after %ds: %s", timeout, command[:200])
        return f"[ERROR] El comando expiro despues de {timeout}s."
    except PermissionError:
        return f"[ERROR] Permiso denegado al ejecutar '{command[:200]}'."
    except OSError as e:
        return f"[ERROR] Error del sistema: {e}"
    except Exception as e:
        logger.exception("Error executing command: %s", command[:200])
        return f"[ERROR] Error inesperado: {e}"
