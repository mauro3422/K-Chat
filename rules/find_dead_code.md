# find_dead_code
**Detecta código no referenciado. Busca funciones, clases, y exports que están definidos pero nadie importa fuera de su propio archivo. También puede detectar imports no utilizados en un archivo.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `dead_imports` | boolean | No | true | Si True, también detecta imports no utilizados en el archivo (default: True) |
| `exclude_tests` | boolean | No | true | Si True, excluye archivos de tests del análisis (default: True) |
| `path` | string | Sí |  | Ruta de archivo o directorio a analizar |
