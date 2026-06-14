# run_code
**Ejecuta codigo Python de forma segura en un entorno aislado (sandbox). No puede acceder a tu sistema de archivos ni importar modulos peligrosos. Si hay errores de sintaxis, intenta corregirlos automaticamente y re-ejecuta. Devuelve JSON estructurado con stdout, stderr, exit_code y auto_fix.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `code` | string | Sí |  | El codigo Python a ejecutar |
| `timeout` | integer | No | 15 | Tiempo maximo en segundos (default: 15, max: 60) |
