# search_files
**Busca un patron de texto en archivos del proyecto. Muestra las lineas donde aparece con contexto, detecta en que funcion/clase esta cada coincidencia (Python con AST), y muestra estadisticas. Similar a grep pero mas legible.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `case_sensitive` | boolean | No | False | Busqueda exacta (default: false = ignora mayusculas/minusculas) |
| `context_lines` | integer | No | 2 | Lineas de contexto antes y despues de cada coincidencia (default: 2, max: 10) |
| `file_pattern` | string | No |  | Filtro glob para archivos (ej: '*.py', '*.md', '*.{py,js}'). Vacio = todos. |
| `max_results` | integer | No | 50 | Maximo de coincidencias a mostrar (default: 50, max: 200) |
| `path` | string | No | ~/proyectos | Directorio donde buscar (default: ~/proyectos) |
| `pattern` | string | Sí |  | El texto o patron a buscar (no es regex, es busqueda literal) |
