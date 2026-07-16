# move_file
**Mueve, renombra o copia archivos y directorios. Reemplaza mv y cp. Operaciones: 'move' (mover/renombrar), 'copy' (copiar). El destino puede ser un directorio (preserva nombre) o una ruta completa.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `dest` | string | Sí |  | Ruta de destino (archivo o directorio) |
| `operation` | string | No | move | 'move' = mover/renombrar, 'copy' = copiar Values: move, copy |
| `source` | string | Sí |  | Ruta del archivo o directorio origen |
