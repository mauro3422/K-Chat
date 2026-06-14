# read_file
**Reads the contents of a system file (e.g. config.py, AGENTS.md, etc.) in a paginated, numbered format.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `end_line` | integer | No |  | End line to read the file up to (inclusive). By default reads the whole file. Max 500 lines per call. |
| `max_lines` | integer | No | 250 | Max lines to return (default: 250, max: 500). Use this to control how much you read. |
| `path` | string | Sí |  | The path to the file to read. Can be relative to the project or absolute (supports '~'). |
| `start_line` | integer | No |  | Start line to read the file from (1-indexed). Default is 1. |
