# list_files
**Lista archivos en un directorio con informacion detallada: lineas de codigo, lenguaje, funciones definidas, clases, imports. Analiza Python con AST (funciones, clases, imports) y otros lenguajes con regex (JS/TS, HTML, Markdown). Ideal para tener una vista rapida de la estructura del proyecto.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `depth` | integer | No | 1 | Profundidad de subdirectorios (default: 1, max: 3, 0 = solo el directorio actual) |
| `path` | string | No | ~/proyectos | Directorio a listar (default: ~/proyectos) |
| `pattern` | string | No |  | Filtro glob opcional (ej: '*.py', '*.md', '*test*'). Vacio = todos los archivos. |
| `show_imports` | boolean | No | False | Mostrar imports/requires del archivo (default: false) |