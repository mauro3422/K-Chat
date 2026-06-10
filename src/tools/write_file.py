import os
from src.paths import CONTEXT_DIR
from src.tools._path_helpers import validate_path as _validate_path

DEFINITION = {
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


def run(path: str, content: str, _session_id: str | None = None) -> str:
    expanded_path = os.path.expanduser(path)
    if not os.path.isabs(expanded_path):
        expanded_path = os.path.abspath(os.path.join(CONTEXT_DIR, expanded_path))
    
    expanded_path = os.path.realpath(expanded_path)
    err = _validate_path(path, expanded_path)
    if err:
        return err
    
    try:
        resolved_path = os.path.realpath(expanded_path)
        err = _validate_path(path, resolved_path)
        if err:
            return err
        dir_name = os.path.dirname(resolved_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
            
        with open(resolved_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"[OK] File written correctly to '{path}'."
    except Exception:
        return f"[ERROR] Could not write the file to '{path}'."
