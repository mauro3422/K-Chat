# write_file
**Creates or overwrites a file in the system with the provided content. Creates parent directories if they do not exist.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `content` | string | Sí |  | The full text content to write into the file. |
| `path` | string | Sí |  | The path to the file to write. Can be relative to the project or absolute (supports '~'). |