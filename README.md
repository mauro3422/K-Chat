# Kairos

Agente personal minimalista con memoria episodica, herramientas paralelas y dashboard web.
Sin frameworks JS, sin npm, sin gateways complejos. Cada pieza es un archivo independiente.

## Stack

- **Modelos:** big-pickle (default), deepseek-v4-flash-free (fallback) — OpenCode Zen API
- **Chat:** CLI + Web dashboard (FastAPI + HTMX + Jinja2)
- **Memoria:** SQLite persistente (sesiones, mensajes con razonamiento, tool_calls con fases, debug_info)
- **Contexto:** SOUL.md + MEMORY.md + AGENTS.md + TOOLS.md (auto-creados y auto-generados)
- **Frontend:** Sin build step, sin bundles, sin npm. HTML + CSS + JS vanilla (~500 líneas total)

## Estructura

```
├── config.py               → Lee .env, valida keys
├── SOUL.md / MEMORY.md     → Personalidad y datos del usuario (auto-creados)
├── AGENTS.md / TOOLS.md    → Reglas del agente y guía de tools (auto-generados)
├── src/
│   ├── core.py             → Orquestador: contexto, tool loop, history compressor
│   ├── llm.py              → API OpenCode Zen (chat + streaming + detección modelos)
│   ├── memory.py           → SQLite con sesiones, mensajes, tools, debug_info
│   └── tools/
│       ├── __init__.py     → Auto-loader de tools (importlib)
│       ├── web_search.py   → Búsqueda web DuckDuckGo
│       └── get_tool_history.py → El modelo consulta su historial de tools
├── web/
│   ├── server.py           → FastAPI (streaming NDJSON, sidebar, debug)
│   ├── templates/chat.html → Jinja2 template
│   └── static/
│       ├── style.css       → Tema oscuro, layout responsive, debug panel
│       ├── session.js      → Sidebar interactiva (rename, delete, navegación)
│       ├── debug.js        → Panel de depuración en vivo
│       └── chat-stream.js  → Streaming NDJSON, razonamiento por fases, tool pills
├── tests/                  → 23 tests (memory CRUD, tool loop, streaming, SESSION_ID)
└── memory/                 → Base de datos SQLite
```

## Funcionalidades

### Streaming con fases visuales
Cada interacción se muestra en fases secuenciadas: razonamiento → tools → razonamiento → tools → respuesta final. Las tools se muestran como pills con spinner (calling) y checkmark (ok).

### Tools paralelas
El modelo puede llamar múltiples tools en una sola iteración. Se ejecutan en paralelo vía `ThreadPoolExecutor`. Los resultados llegan a medida que se completan.

### Dashboard web
- Sidebar con sesiones (renombrar, eliminar, navegar)
- Histórico con razonamiento y tools preservado post-F5
- Panel Debug en vivo: modelo, razonamiento, tools, system prompt, stream log, UI log

### Memoria episódica
Cada tool call se loguea con timestamp, input, status y número de fase. Las fases de razonamiento se guardan como JSON para reconstruir la secuencia visual post-refresh.

### Contexto dinámico
SOUL.md, MEMORY.md, AGENTS.md se auto-crean al primer arranque. TOOLS.md se auto-genera desde el registry de tools. `get_tool_history` permite al modelo consultar su propio historial.

### History compressor
Cuando la conversación supera 40 mensajes, resume los antiguos vía LLM.

## Arranque

```bash
# CLI
python -m src.cli

# Web dashboard
python web/server.py
# → http://127.0.0.1:8000
```

## Tests

```bash
python -m pytest tests -v
```

## Agregar una tool

Crear un archivo en `src/tools/` con `DEFINITION` + `run()`. Se registra automáticamente.

```python
DEFINITION = {
    "type": "function",
    "function": {
        "name": "mi_tool",
        "description": "Qué hace",
        "parameters": {"type": "object", "properties": {...}}
    }
}

def run(**kwargs) -> str:
    return "resultado"
```

## Filosofía — "Legos"

Cada pieza es independiente y reemplazable:
- Tools → archivos sueltos en `src/tools/`
- Contexto → archivos markdown en la raíz
- Memoria → SQLite puro, sin ORM
- Frontend → HTML + CSS + JS vanilla, sin build step

Lo que no sirve se reemplaza, no se parchea.
