# Kairos — Roadmap

## Filosofía

Un agente que hace lo justo. Sin plugins externos, sin marketplaces, sin gateways complejos.
Cada pieza es un archivo independiente ("legos").

## ✅ Completado

- **Núcleo**: `config.py` → `src/llm.py` → `src/memory.py` → `src/core.py`
- **Tools pipeline**: auto-load (importlib), paralelo (ThreadPoolExecutor), history compressor
- **Dashboard web**: FastAPI + HTMX + Jinja2 (sin build step), streaming NDJSON, razonamiento por fases, tool pills, sidebar, debug panel
- **Persistencia visual post-F5**: `turn` en tool_calls, `phases` JSON en messages, intercalado razonamiento↔tools en histórico
- **Calidad**: Tests pasando, WAL mode, try/finally, logging, tipos, sin bare `except:`
- **Tool: save_memory**: Tool que persiste de manera concurrente y robusta datos del usuario en `MEMORY.md`
- **Widgets interactivos**: Renderizado seguro de HTML/JS vivo en chat mediante iFrames con auto-resize y captura de eventos

## 🔲 Próximo

| Prioridad | Área | Qué |
|-----------|------|-----|
| 1 | **Nocturnal agent** | Síntesis diaria de sesiones → MEMORY.md |
| 2 | **Telegram bot** | `bot.py` con python-telegram-bot para chat desde Telegram |
| 3 | **Linux + polish** | Portabilidad `USERNAME`→`USER` (hecho), systemd, Dockerfile, setup.py |


## Decisiones de arquitectura

| Decisión | Elegido | Alternativa |
|----------|---------|-------------|
| Runtime | Python puro | TypeScript |
| LLM client | OpenAI SDK | httpx directo |
| Memory | SQLite nativo | sqlite-vec |
| Stream | sync generator | async |
| Config | python-dotenv | YAML |
| Tools | importlib auto-registry | registro manual |
| Frontend | HTMX + JS vanilla | React / Vue / Svelte |
| Serialización | NDJSON (JSON lines) | SSE |
