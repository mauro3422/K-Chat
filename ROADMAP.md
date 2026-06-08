# Kairos - Roadmap

## Filosofia

Un agente que hace lo justo. Sin plugins externos, sin marketplaces, sin gateways complejos. Cada pieza es un archivo independiente ("legos").

Kairos no intenta ser una copia de OpenClaw. La inspiracion viene de querer un asistente personal que sea util e iterable sin tener que pelear con una plataforma grande, configuraciones fragiles o errores dificiles de rastrear.

El objetivo es construir primero un nucleo estable: conversacion, memoria, tools, streaming, debug y capacidad de mejorar el propio proyecto junto al usuario.

Los canales futuros son importantes, pero deben entrar como adaptadores alrededor del nucleo existente. Telegram, webhooks, tareas nocturnas o integraciones externas no deberian cambiar la esencia del sistema: un wrapper decente, legible y robusto para un asistente personal, no una plataforma inflada desde el dia uno.

## Completado

- **Nucleo**: `config.py` -> `src/llm.py` -> `src/memory.py` -> `src/core.py`
- **Tools pipeline**: auto-load con `importlib`, ejecucion paralela con `ThreadPoolExecutor`, history compressor
- **Dashboard web**: FastAPI + HTMX + Jinja2, streaming NDJSON, razonamiento por fases, tool pills, sidebar, debug panel
- **Persistencia visual post-refresh**: `turn` en `tool_calls`, `phases` JSON en `messages`, intercalado razonamiento/tools en historico
- **Calidad base**: WAL mode, `try/finally`, logging, tipos, sin `except:` desnudos
- **Tool `save_memory`**: persistencia concurrente y robusta de datos del usuario en `MEMORY.md`
- **Widgets interactivos**: renderizado seguro de HTML/JS vivo en chat mediante iframes con auto-resize y captura de eventos

## Proximo

| Prioridad | Area | Que |
|-----------|------|-----|
| 1 | **Nucleo estable** | Robustecer streaming, errores, memoria, tools y tests antes de sumar complejidad |
| 2 | **Nocturnal agent** | Sintesis diaria de sesiones hacia `MEMORY.md` |
| 3 | **Telegram bot** | `bot.py` como adaptador hacia `core.chat_stream()`, sin duplicar logica |
| 4 | **Linux + polish** | Portabilidad, systemd, Dockerfile, setup.py |

## Decisiones de arquitectura

| Decision | Elegido | Alternativa |
|----------|---------|-------------|
| Runtime | Python puro | TypeScript |
| LLM client | OpenAI SDK | httpx directo |
| Memory | SQLite nativo + Markdown | sqlite-vec / base externa |
| Stream | Sync generator | Async complejo |
| Config | `.env` + Markdown | YAML grande |
| Tools | `importlib` auto-registry | Registro manual |
| Frontend | HTMX + JS vanilla | React / Vue / Svelte |
| Serializacion | NDJSON | SSE |
| Crecimiento | Canales como adaptadores | Gateway/plataforma pesada desde el inicio |

## Principio guia

Kairos debe crecer desde la utilidad real, no desde la imitacion. Primero tiene que ser un ayudante confiable para el usuario y para su propio codigo; despues puede sumar canales, automatizaciones y capacidades externas sin perder legibilidad.
