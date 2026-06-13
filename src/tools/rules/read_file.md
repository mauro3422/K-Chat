# read_file
**Reads the contents of a system file (e.g. config.py, AGENTS.md, etc.) in a paginated, numbered format.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `end_line` | integer | No |  | End line to read the file up to (inclusive). By default reads the whole file, but output is capped at 100 lines per call to prevent token overflow. Use multiple calls with start_line to read large files. |
| `path` | string | Sí |  | The path to the file to read. Can be relative to the project or absolute (supports '~'). |
| `start_line` | integer | No | 1 | Start line to read the file from (1-indexed). Default is 1. |