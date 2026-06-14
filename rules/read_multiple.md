# read_multiple
**Lee MULTIPLES archivos en UNA sola llamada. Cada archivo puede incluir un rango de lineas (ej: 'src/core/tool_loop.py:1-50'). Acepta hasta 10 archivos por call, hasta 250 lineas cada uno (max 500 con max_lines). Ideal para leer modulos completos o comparar archivos relacionados.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `files` | array | Sí |  | Lista de rutas a leer. Cada ruta puede incluir rango: 'archivo.py' (completo), 'archivo.py:20-50' (lineas 20 a 50), 'archivo.py:30' (desde linea 30). Max 10 archivos. |
| `max_lines` | integer | No | 250 | Max lineas por archivo (default: 250, max: 500) |
