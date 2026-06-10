import os
from src.paths import CONTEXT_DIR
from src.tools._path_helpers import validate_path as _validate_path

DEFINITION = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Reads the contents of a system file (e.g. config.py, AGENTS.md, etc.) in a paginated, numbered format.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the file to read. Can be relative to the project or absolute (supports '~')."
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line to read the file from (1-indexed). Default is 1."
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line to read the file up to (inclusive). By default reads the whole file, but output is capped at 100 lines per call to prevent token overflow. Use multiple calls with start_line to read large files."
                }
            },
            "required": ["path"]
        }
    }
}


def _paginate_and_format(path: str, lines: list[str], start_line: int, end_line: int | None) -> str:
    total_lines = len(lines)

    try:
        start_line = max(1, int(start_line))
    except (ValueError, TypeError):
        start_line = 1

    if end_line is not None:
        try:
            end_line = min(total_lines, max(start_line, int(end_line)))
        except (ValueError, TypeError):
            end_line = total_lines
    else:
        end_line = total_lines

    MAX_LINES_PER_CALL = 100
    requested_count = end_line - start_line + 1
    was_truncated = False
    if requested_count > MAX_LINES_PER_CALL:
        end_line = start_line + MAX_LINES_PER_CALL - 1
        was_truncated = True

    output_lines = []
    for idx in range(start_line - 1, end_line):
        line_num = idx + 1
        line_content = lines[idx]
        output_lines.append(f"{line_num}: {line_content}")

    content_str = "".join(output_lines)

    metadata = f"[File: {path} | Total lines: {total_lines} | Displayed range: {start_line}-{end_line}]\n"
    if was_truncated:
        metadata += f"[NOTE: Output truncated to {MAX_LINES_PER_CALL} lines. To read more, call again with start_line={end_line + 1}]\n"
    return metadata + content_str


def run(path: str, start_line: int = 1, end_line: int | None = None, _session_id: str | None = None) -> str:
    expanded_path = os.path.expanduser(path)
    if not os.path.isabs(expanded_path):
        expanded_path = os.path.abspath(os.path.join(CONTEXT_DIR, expanded_path))
    
    expanded_path = os.path.realpath(expanded_path)
    err = _validate_path(path, expanded_path)
    if err:
        return err
    
    if not os.path.exists(expanded_path):
        return f"[ERROR] The file '{path}' does not exist."
    
    if os.path.isdir(expanded_path):
        return f"[ERROR] '{path}' is a directory, not a file."
        
    try:
        resolved_path = os.path.realpath(expanded_path)
        err = _validate_path(path, resolved_path)
        if err:
            return err
        with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        return _paginate_and_format(path, lines, start_line, end_line)
    except Exception:
        return f"[ERROR] Could not read the file '{path}'."
