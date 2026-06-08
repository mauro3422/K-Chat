# Arquitectura

## Filosofía "Legos"

Cada pieza es un bloque independiente que se conecta por interfaces mínimas.
No hay framework central, no hay plugin loader mágico, no hay DI container.
Cada archivo se puede leer y entender solo.

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  tools/     │◄────┤   core.py    ├────►│  llm.py     │
│  (autoload) │     │ (orquestador)│     │ (API client)│
└──────┬──────┘     └──────┬───────┘     └─────────────┘
       │                   │
       ▼                   ▼
┌──────────────┐    ┌──────────────┐
│  memory.py   │    │  web/server  │
│  (SQLite)    │    │  (FastAPI)   │
└──────────────┘    └──────┬───────┘
                           │
                    ┌──────┴───────┐
                    │  browser     │
                    │  HTMX + JS   │
                    └──────────────┘
```

## Flujo de datos (streaming)

```
Usuario → Form POST → server.py → core.chat_stream()
                                         │
                          ┌────────────────┴────────────────┐
                          │  LLM call con tools=TOOLS       │
                          │  if tool_calls:                 │
                          │    turn++                       │
                          │    yield ("reasoning", rc)      │
                          │    yield ("reasoning", content) │
                          │    yield ("tool_call", calling) │
                          │    parallel execute via pool    │
                          │    yield ("tool_call", result)  │
                          │    log_tool_call(turn=N)        │
                          │    LLM call again               │
                          └────────────────┬────────────────┘
                                           │
                          ┌────────────────┴────────────────┐
                          │  yield ("reasoning", final_rc)  │
                          │  yield ("content", tokens...)   │
                          │  save_message(phases=JSON)      │
                          └────────────────┬────────────────┘
                                           │
                    ┌──────────────────────┴──────────────┐
                    │  NDJSON → browser JS reads stream   │
                    │  reasoning → <details> por fase     │
                    │  tool_call → pills con spinner/✓    │
                    │  content → msg-body token a token   │
                    └─────────────────────────────────────┘
```

## Piezas

### tools/ — Auto-registry

Cada archivo en `src/tools/` exporta `DEFINITION` (dict OpenAI-compatible) y `run(**kwargs) → str`.
`__init__.py` los escanea con `importlib.import_module()`, construye `TOOLS` y `TOOL_MAP`.
No hay registro manual, no hay decoradores, no hay archivos de configuración.

### core.py — Orquestador

- `load_context()`: lee SOUL.md, MEMORY.md, AGENTS.md, genera TOOLS.md
- `chat_stream()`: generador que yield eventos NDJSON
  1. Construye system prompt + history
  2. Llama LLM con tools
  3. Si tool_calls → turno++, ejecuta tools en paralelo, logea con `turn`
  4. Llama LLM otra vez con resultados
  5. Al terminar: yield contenido final
- `phases_output`: captura `{reasoning, tool_ids}` por turno para guardar en DB

### memory.py — SQLite puro

Cada función crea su propia conexión con `get_conn()`, con `try/finally` para liberar recursos.
WAL mode + busy timeout para concurrencia. Tablas:
- `messages`: id, session_id, role, content, model, reasoning, phases(JSON), created_at
- `tool_calls`: id, session_id, tool_name, input, status, turn, created_at
- `sessions`: session_id, name, created_at
- `debug_info`: session_id + columnas de depuración

### web/ — Dashboard

- `server.py`: FastAPI con rutas streaming, sidebar, rename, delete, debug
- `static/style.css`: ~100 líneas, tema oscuro, debug panel slide, tool pills
- `static/session.js`: sidebar interactiva
- `static/debug.js`: panel debug con stream log y UI log
- `static/chat-stream.js`: consume NDJSON, construye fases, tool pills, body
- `templates/chat.html`: ~45 líneas, Jinja2 con `{{ session_id }}` y `{{ model }}`

## Wire format

```
NDJSON (application/x-ndjson)

{"t":"reasoning","d":"thinking..."}      → nueva fase de razonamiento
{"t":"tool_call","d":"{\"id\":\"c1\",...}"} → calling / result
{"t":"content","d":" token"}             → token de respuesta final
```

## Contexto (system prompt)

```
SOUL.md     → personalidad, tono
MEMORY.md   → datos del usuario
AGENTS.md   → reglas de comportamiento
TOOLS.md    → guía de herramientas (auto-generado)
```

Se concatenan en el system prompt. Cada archivo es markdown plano que el modelo lee.

## Persistencia visual post-refresh

El streaming construye: `<details>razonamiento(1)</details>` → `<pills(1)>` → `<details>razonamiento(2)</details>` → `<pills(2)>` → `<body>`.

Para preservar esto en el histórico, cada tool loop se numera (`turn`) y el razonamiento se guarda por fase (`phases` JSON). En el GET `/sessions/{id}/messages`, el servidor intercala razonamiento y tools usando estos datos.

## Visión Linux

El proyecto es mayormente portable. 

Puntos resueltos:
- `os.environ.get("USERNAME")` → `os.environ.get("USER") or os.environ.get("USERNAME", "user")`
- Paths absolutos → `Path(__file__).parent`
- DuckDuckGo `ddgs` funciona igual en Linux
- SQLite es nativo
- WAL mode + busy timeout para filesystem NFS

Pendiente: sistema de archivos (separador `/` vs `\`), systemd unit, Dockerfile.
