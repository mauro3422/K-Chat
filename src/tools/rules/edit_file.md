# edit_file
**Edita lineas especificas de un archivo sin tener que reescribirlo completo. Usalo cuando sepas las lineas exactas a modificar (obtenidas con search_files o list_files). Soporta reemplazar rangos de lineas, insertar en una posicion, o eliminar lineas. Mucho mas eficiente que read_file + write_file.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `end_line` | integer | No |  | Linea de fin (inclusive). Opcional: si solo start_line → inserta antes de esa linea. Si start_line + end_line → reemplaza ese rango. Si start_line + end_line + new_content vacio → borra ese rango. |
| `new_content` | string | No |  | El nuevo contenido a poner en lugar de las lineas. Si esta vacio y hay start/end_line, se borran esas lineas. |
| `path` | string | Sí |  | Ruta del archivo a editar (absoluta o relativa) |
| `start_line` | integer | Sí |  | Linea de inicio (1-indexed). Para reemplazar: desde esta linea. Para insertar: despues de esta linea (si no hay end_line). Para eliminar: desde esta linea (si new_content vacio). |