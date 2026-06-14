import os
from typing import Any
from src.tools._path_helpers import resolve_and_validate_path

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Creates or overwrites a file in the system with the provided content. Creates parent directories if they do not exist.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the file to write. Can be relative to the project or absolute (supports '~')."
                },
                "content": {
                    "type": "string",
                    "description": "The full text content to write into the file."
                }
            },
            "required": ["path", "content"]
        }
    }
}


async def run(**kwargs) -> str:
    path = kwargs.get("path") or kwargs.get("file_path") or kwargs.get("filepath", "")
    content = kwargs.get("content") or kwargs.get("data") or kwargs.get("text", "")
    _session_id = kwargs.get("_session_id")
    resolved, err = resolve_and_validate_path(path)
    if err:
        return err

    import asyncio
    import os

    try:
        from src.tools._preflight import create_backup, postflight_check, rollback

        # Backup if file exists
        backup_path = None
        if os.path.exists(resolved):
            backup_path = create_backup(resolved)

        def _write_sync():
            dir_name = os.path.dirname(resolved)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(resolved, "w", encoding="utf-8") as f:
                f.write(content)

        await asyncio.to_thread(_write_sync)

        # Post-flight validation
        pf = postflight_check(resolved, content)
        if not pf["ok"]:
            if backup_path:
                rollback(resolved, backup_path)
                return f"[ERROR] Post-flight falló after write (rollback applied): {'; '.join(pf['errors'][:3])}"
            return f"[ERROR] Post-flight falló: {'; '.join(pf['errors'][:3])}"

        msg = f"[OK] File written correctly to '{path}'."
        if pf["warnings"]:
            msg += " " + "; ".join(pf["warnings"][:2])
        return msg
    except Exception:
        return f"[ERROR] Could not write the file to '{path}'."
