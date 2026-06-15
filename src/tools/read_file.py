import os
from typing import Any
from src.tools._path_helpers import resolve_and_validate_path

DEFINITION: dict[str, Any] = {
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
                    "description": "End line to read the file up to (inclusive). By default reads the whole file. Max 500 lines per call."
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Max lines to return (default: 250, max: 500). Use this to control how much you read.",
                    "default": 250
                }
            },
            "required": ["path"]
        }
    }
}


def _paginate_and_format(path: str, lines: list[str], start_line: int, end_line: int | None, max_lines: int = 250) -> str:
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

    MAX_LINES_PER_CALL = max_lines
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


async def run(**kwargs) -> str:
    path = kwargs.get("path") or kwargs.get("file_path") or kwargs.get("filepath", "")
    start_line = int(kwargs.get("start_line", kwargs.get("start", 1)))
    end_line = kwargs.get("end_line", kwargs.get("end"))
    max_lines = min(int(kwargs.get("max_lines", 250)), 500)
    _session_id = kwargs.get("_session_id")
    resolved, err = resolve_and_validate_path(path)
    if err:
        return err

    import os
    import os

    if not await asyncio.to_thread(os.path.exists, resolved):
        return f"[ERROR] The file '{path}' does not exist."

    if await asyncio.to_thread(os.path.isdir, resolved):
        return f"[ERROR] '{path}' is a directory, not a file."

    try:
        def _read_sync():
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                return f.readlines()
        
        lines = await asyncio.to_thread(_read_sync)

        return _paginate_and_format(path, lines, start_line, end_line, max_lines)
    except Exception:
        return f"[ERROR] Could not read the file '{path}'."
