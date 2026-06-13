> ⚠️ This document may lag behind the current version. See [docs/ARCHITECTURE.md](ARCHITECTURE.md) and [docs/MODULES.md](MODULES.md) for the latest.

# Arquitectura de `src/tools/`

## 1. Qué hace cada archivo

| Archivo | Función |
|---------|---------|
| `__init__.py` | Expone `TOOLS` (definition única para el LLM), `TOOL_MAP` y `run_parallel_tools`. |
| `loader.py` | Auto-discovery: escanea `.py` del directorio y registra `DEFINITION` + `run` en `TOOL_MAP`. |
| `runner.py` | Ejecuta batch de tool_calls en paralelo con `ThreadPoolExecutor`, parsea, valida rate-limit, persiste. |
| `_rate_limiter.py` | Sliding window de 30 llamadas por 10s por session (thread-safe con lock). |
| `_tool_parser.py` | Desempaqueta `execute_action` → extrae `action_name`/`arguments`, valida required params. |
| `_tool_persister.py` | Inserta cada tool_call y resultado en SQLite (tablas `tool_calls` + `messages`). |
| `_path_helpers.py` | Resuelve paths y valida que estén dentro de project_root, home o /tmp (previene path traversal). |
| `_widget_helpers.py` | Repo singleton de widgets, sanitiza `widget_id`, valida session_id. |
| `_analyzers.py` | Helpers de análisis: detección de lenguaje, análisis AST Python, regex para JS/TS/MD/HTML/CSS, iconos por lenguaje. |
| `_validators.py` | Validación de sintaxis para Python (AST), JavaScript (node --check), JSON, HTML, CSS, YAML, TOML. Usado por `write_file` post-write. |
| `execute_command.py` | Ejecuta comandos shell con timeout, cwd configurable y bloqueo básico de patrones peligrosos. |
| `list_files.py` | `ls` mejorado con análisis de lenguaje, funciones, clases, imports y estructura de directorios. |
| `search_files.py` | Búsqueda tipo grep con contexto, detección de función/clase, estadísticas, brace globs `*.{py,js}`. |
| `edit_file.py` | Edición quirúrgica de líneas: reemplazar rango, insertar, eliminar. Sin reescribir archivos enteros. |
| `analyze_code.py` | Análisis profundo Python con AST: funciones, parámetros, call graph, imports, métricas por función. |
| `web_search.py` | Busca en SearXNG local con retry, formato de resultados, infoboxes y suggestions. |
| `fetch_url.py` | Descarga página web, extrae texto con lxml, anti-SSRF, detección de binarios, retry. |
| `read_file.py` | Lee archivo con paginación (100 líneas max/call), formato numerado, validación de path. |
| `write_file.py` | Crea/sobreescribe archivo, crea directorios padres si faltan, validación de path + validación post-write. |
| `save_memory.py` | Lee/escribe `MEMORY.md` con sección `## Memories`, thread-safe con lock, reparación de header corrupto, invalida cache de contexto. |
| `read_skill.py` | Lee archivos `.md` de `skills/`, sanitiza nombre, lista skills disponibles si no existe. |
| `get_tool_history.py` | Consulta historial de tool_calls de la sesión actual desde SQLite. |
| `save_widget.py` | Guarda widget como oficial (versionado auto-incremental) en la DB. |
| `update_widget.py` | Actualiza widget existente como nueva versión (requiere code). |
| `get_widget_code.py` | Recupera código + metadata de un widget oficial desde la DB. |
| `git_operation.py` | Operaciones Git seguras (status, diff, log, branch, add, commit, push, pull, clone). Bloquea `--force`/`--hard`. |

## 2. Auto-discovery (`loader.py`)

```
src/tools/
  __init__.py      ← ignorado (startswith '__')
  runner.py        ← ignorado (excluido explícitamente)
  _rate_limiter.py ← ignorado (startswith '__' — no, empieza con _ pero se prueba)
  loader.py        ← ignorado (empieza con 'runner' check... no)
  web_search.py    ← IMPORTADO ✓
  ...
```

El loader itera `os.listdir()` del directorio `src/tools/`, filtrando:
- Excluye `__*.py` (con `startswith('__')`)
- Excluye `runner.py` explícitamente
**Nota**: `_rate_limiter.py`, `_tool_parser.py`, `_tool_persister.py`, `_path_helpers.py`, `_widget_helpers.py`, `_analyzers.py`, `_validators.py` no empiezan con `__`, pero no exportan `DEFINITION` ni `run`, así que se descartan silenciosamente.

**Total**: 16 tools auto-descubiertas (v0.0.52+).
- Requiere `DEFINITION` (dict con schema OpenAI) y `run` (callable)
- Extrae `tool_name` de `DEFINITION['function']['name']`
- Registra en `TOOL_MAP[tool_name] = mod.run` y `TOOL_DEFINITIONS[tool_name] = mod.DEFINITION`
- Errores se loguean y el tool se ignora silenciosamente

**Nota**: `_rate_limiter.py`, `_tool_parser.py`, `_tool_persister.py`, `_path_helpers.py`, `_widget_helpers.py` no empiezan con `__`, pero no exportan `DEFINITION` ni `run`, así que se descartan con el warning.

## 3. Runner (`runner.py`)

Flujo de `run_parallel_tools()`:

1. **Parse**: `_prepare_tool_calls()` itera cada `tc`, llama `_parse_tool_call()` que:
   - Desempaqueta `execute_action` → `(action_name, arguments)`
   - Valida que el nombre exista en `tool_map`
   - Valida required params contra `TOOLS` definition
   - Si hay error, registra en history y continúa

2. **Rate limit**: `_check_rate_limit(session_id)` — 30 llamadas / 10s sliding window

3. **Ejecución paralela**: `_execute_tool_batch()` usa `ThreadPoolExecutor(max_workers=N)` donde N = número de tools. Cada tool se ejecuta como `tool_map[name](**args, _session_id=session_id)`.

4. **Persistencia**: `_persist_tool_results()` inserta en SQLite dentro de una transacción:
   - `tool_calls`: session_id, tool_name, input (JSON), status, turn, created_at
   - `messages`: session_id, role="tool", content=result, tool_call_id

5. **Truncado**: Resultados > 30.000 chars se truncan con `...[truncado]`

## 4. Patrón de cada tool

Cada tool es un módulo `.py` con dos exports obligatorios:

```python
# 1. DEFINITION — schema OpenAI Function Calling
DEFINITION = {
    "type": "function",
    "function": {
        "name": "nombre_unico",
        "description": "...",
        "parameters": {
            "type": "object",
            "properties": { ... },
            "required": ["param1", ...]
        }
    }
}

# 2. run() — lógica de ejecución
def run(param1: str, param2: int = 0, _session_id: str | None = None) -> str:
    # Validar inputs
    # Ejecutar lógica
    # Retornar string ("[OK]...", "[ERROR]...", o resultado)
```

**Convenciones observadas**:
- `_session_id` es inyectado por el runner, no es param del LLM
- `_retries` se usa en tools de red (web_search, fetch_url)
- Retornos exitosos: string plano
- Retornos de error: prefijo `[ERROR]`
- `_path_helpers` se usa en tools de filesystem
- `_widget_helpers` se usa en tools de widgets

## 5. Helpers — qué comparten

| Helper | Usado por | Función |
|--------|-----------|---------|
| `_path_helpers` | `read_file`, `write_file` | `resolve_and_validate_path()` — resuelve path relativo/absoluto y valida sandbox (project_root, home, /tmp) |
| `_widget_helpers` | `save_widget`, `update_widget`, `get_widget_code` | `validate_widget_args()`, `sanitize_widget_id()`, `get_saved_widget_repo()` — repo singleton + sanitización |
| `_rate_limiter` | `runner.py` | Sliding window rate limit por session |
| `_tool_parser` | `runner.py` | Desempaqueta `execute_action`, valida params |
| `_tool_persister` | `runner.py` + `get_tool_history` | Persiste tool_calls en SQLite |

## 6. Lo que está bien

- **Auto-discovery limpio**: Añadir una tool es solo crear el `.py` con `DEFINITION` + `run`. No hay que tocar config central.
- **Separación clara**: Runner se encarga de orquestación (parse, rate-limit, parallel, persist). Tools solo implementan lógica.
- **Seguridad**: Path traversal mitigado (`_path_helpers`), SSRF protection en `fetch_url` (resolución DNS + IP check), sanitización de widget_id, rate limiting.
- **Observabilidad**: Logging en cada punto, tool_calls persistidos en SQLite, status "ok"/"error" en cada resultado.
- **Idempotencia de imports**: `__init__.py` construye `TOOLS` una vez, `loader.py` llena `TOOL_MAP` una vez. Thread-safe por diseño (single-threaded import).
- **Reintentos**: `web_search` (2 retries) y `fetch_url` (1 retry) con backoff.
- **Bootstrap de SearXNG**: el arranque no instala dependencias por defecto; la instalación debe activarse explícitamente con `SEARXNG_AUTO_INSTALL=1`.
- **Truncado de seguridad**: Resultados > 30K chars y archivos > 100 líneas se cortan para evitar overflow de tokens.

## 7. Lo que podría mejorar

- **`_tool_parser` usa import circular**: `_get_required_params()` importa `src.tools.TOOLS` que a su vez importa `loader.py`. Funciona por lazy import, pero es frágil.
- **`_tool_persister` accede a `conn` internals**: Llama `tool_call_repo._get_conn()` (método privado) para hacer SQL directo. Rompe encapsulamiento del repo.
- **`runner.py` importa `_tool_persister` inline**: Dentro de `_prepare_tool_calls` hace `from src.tools._tool_persister import _get_tool_call_repo` para evitar circular import. Mejor mover a top-level o refactorizar dependencias.
- **`save_memory.py` tiene su propio lock**: Mientras `runner.py` ejecuta tools en paralelo, `save_memory` serializa con `_save_lock`. Esto puede causar cuellos de botella si se usa `save_memory` frecuentemente.
- **No hay validación de tipos en `run()`**: El parser extrae args como `dict`, pero `run()` los desempaqueta con `**args`. Si el LLM envía un tipo incorrecto (ej: `max_results="abc"`), falla con un error genérico en vez de un mensaje claro.
- **`read_file` lee todo el archivo a memoria**: `f.readlines()` carga el archivo completo antes de paginar. Para archivos grandes esto es ineficiente.
- **Falta tests unitarios en el directorio**: No hay `tests/` dedicado a tools. Los helpers (`_path_helpers`, `_rate_limiter`) serían fáciles de testear.
- **`fetch_url` no soporta JavaScript**: El extractor de texto con lxml solo parsea HTML estático. Podría ofrecer fallback con `playwright` para SPAs.
