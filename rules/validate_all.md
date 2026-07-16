# validate_all
**Valida la sintaxis de MULTIPLES archivos Python, JS, JSON, HTML, CSS en UNA sola llamada. Usa los validadores internos segun la extension de cada archivo. Devuelve un resumen con cuantos pasaron, fallaron o fueron omitidos. Opcionalmente verifica reglas arquitectónicas (modo architecture).**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `architecture` | boolean | No | false | Si True, también verifica reglas arquitectónicas Legos (upward coupling, framework imports, etc.). Default: False. |
| `files` | array | No |  | Lista de rutas de archivos a validar. Max 20 archivos. |
| `path` | string | No |  | Directorio a escanear (profundidad 1) en lugar de lista de archivos. Opcional si ya pasaste 'files'. |
| `pattern` | string | No |  | Filtro glob para archivos (ej: '*.py', '*.{py,js}'). Solo si usas 'path'. |
