import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

DEFINITION = {
    "type": "function",
    "function": {
        "name": "git_operation",
        "description": "Run safe Git operations (status, diff, log, branch, add, commit, push, pull, clone). Destructive operations (push --force, reset --hard) are BLOCKED.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["status", "diff", "log", "branch", "add", "commit", "push", "pull", "clone"],
                    "description": "Git operation to perform"
                },
                "path": {
                    "type": "string",
                    "description": "File path for add operation, or clone URL/directory"
                },
                "message": {
                    "type": "string",
                    "description": "Commit message (required for commit operation)"
                },
                "count": {
                    "type": "integer",
                    "description": "Number of commits for log/diff (default: 5)"
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (default: $HOME)"
                }
            },
            "required": ["operation"]
        }
    }
}

MAX_OUTPUT = 30000
TIMEOUT = 60

BLOCKED_PATTERNS = [
    " --force",
    " --hard",
    " reset ",
    " clean -fd",
    " rm ",
]


def _is_blocked(command: str) -> tuple[bool, str]:
    cmd_lower = command.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            return True, (
                f"Blocked: command contains '{pattern.strip()}'. "
                "Destructive Git operations are not allowed."
            )
    return False, ""


def _build_command(operation: str, path: str | None, message: str | None, count: int) -> list[str]:
    if operation == "status":
        return ["git", "status", "--short"]
    elif operation == "diff":
        if count and count > 1:
            return ["git", "diff", f"HEAD~{count}"]
        return ["git", "diff"]
    elif operation == "log":
        return ["git", "log", "--oneline", f"-{count}"]
    elif operation == "branch":
        return ["git", "branch", "-a"]
    elif operation == "add":
        if not path:
            raise ValueError("path is required for add operation")
        return ["git", "add", path]
    elif operation == "commit":
        if not message:
            raise ValueError("message is required for commit operation")
        return ["git", "commit", "-m", message]
    elif operation == "push":
        return ["git", "push"]
    elif operation == "pull":
        return ["git", "pull"]
    elif operation == "clone":
        if not path:
            raise ValueError("path (URL) is required for clone operation")
        return ["git", "clone", path]
    else:
        raise ValueError(f"Unknown operation: {operation}")


def run(**kwargs: Any) -> str:
    operation = kwargs.get("operation", "")
    path = kwargs.get("path")
    message = kwargs.get("message")
    count = kwargs.get("count", 5)
    cwd = kwargs.get("cwd", os.environ.get("HOME", "."))

    if not operation:
        return "[ERROR] No operation provided."

    resolved_cwd = os.path.expanduser(cwd)
    if not os.path.isdir(resolved_cwd):
        return (
            f"[ERROR] The directory '{cwd}' does not exist. "
            f"Make sure the folder exists or pass a valid cwd."
        )

    try:
        cmd_parts = _build_command(operation, path, message, count)
    except ValueError as e:
        return f"[ERROR] {e}"

    cmd_str = " ".join(cmd_parts)

    blocked, msg = _is_blocked(cmd_str)
    if blocked:
        return f"[ERROR] {msg}"

    logger.info("Git operation: %s (cwd=%s)", cmd_str, resolved_cwd)

    try:
        result = subprocess.run(
            cmd_parts,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            cwd=resolved_cwd,
        )

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n--- STDERR ---\n{result.stderr}"
        if result.returncode != 0:
            output = f"[EXIT CODE: {result.returncode}]\n{output}"

        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + "\n...[truncated to 30000 chars]"

        return output if output else "(no output)"

    except subprocess.TimeoutExpired:
        logger.warning("Git operation timed out after %ds: %s", TIMEOUT, cmd_str)
        return f"[ERROR] Git operation timed out after {TIMEOUT}s."
    except PermissionError:
        return f"[ERROR] Permission denied running '{cmd_str}'."
    except OSError as e:
        return f"[ERROR] System error: {e}"
    except Exception as e:
        logger.exception("Error in git operation: %s", cmd_str)
        return f"[ERROR] Unexpected error: {e}"
