# execute_command
**Ejecuta un comando en tu terminal Linux. Usalo para correr scripts, compilar codigo, mover archivos, instalar paquetes, buscar archivos con grep, etc. Soporta operadores de shell (&&, |, >, etc.) y funciona en Linux y Windows. El working directory default es ~/proyectos. El output se trunca a 30000 caracteres.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `command` | string | Sí |  | El comando a ejecutar (ej: 'ls -la', 'cd src && python3 script.py', 'dir', 'echo hola') |
| `cwd` | string | No | ~/proyectos | Directorio de trabajo (default: ~/proyectos, '~' = home del usuario) |
| `timeout` | integer | No | 30 | Tiempo maximo en segundos (default: 30, max: 120) |
