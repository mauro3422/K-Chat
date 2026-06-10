# Kairos - Roadmap

## Philosophy

An agent that does just enough. No external plugins, no marketplaces, no complex gateways. Each piece is an independent file ("legos").

Kairos is not trying to be a copy of OpenClaw. It is born from the frustration of configuring a large platform, finding errors when trying to use it for real tasks, and wanting something more direct: a personal assistant that can chat, remember, use tools, show what it did, and iterate on its own project alongside the user.

The goal is to build a reliable core first: chat, memory, tools, streaming, debug, and the ability to evolve without fighting an opaque architecture. Future channels like Telegram, webhooks, or nightly tasks should be adapters around the same core, not a reason to turn the project into a bloated platform.

## Completed

- **Core**: `config.py` → `src/llm/` → `src/memory/` → `src/core/`
- **Tools pipeline**: auto-load with `importlib`, parallel execution with `ThreadPoolExecutor`, history compressor
- **Dashboard web**: FastAPI + vanilla JS, streaming NDJSON, reasoning by phases, tool pills, sidebar, debug panel
- **Visual persistence post-refresh**: `turn` in `tool_calls`, `phases` JSON in `messages`, interleaved reasoning/tools in history
- **Base quality**: WAL mode, `try/finally`, logging, types, no bare `except:`
- **Tool `save_memory`**: concurrent and robust persistence of user data to `MEMORY.md`
- **Interactive widgets**: safe rendering of live HTML/JS in chat via sandboxed iframes with auto-resize and event capture
- **Widget system official**: DB persistence, versioning (v1→v2→...), toolbar with edit/reset/history
- **Auto-generated TOOLS.md**: linked to `TOOL_DEFINITIONS`, regenerates on startup
- **URL fetch tool**: `fetch_url` with SSRF protection, text extraction, retry logic
- **Unified prompt language**: all system files in English, response in user's language
- **Self-awareness rules**: identity and model awareness in system prompt + AGENTS.md
- **Context cleanup**: no duplicate rules between meta block and AGENTS.md

## Next

| Priority | Area | What |
|----------|------|------|
| 1 | **Core stability** | Harden streaming, errors, memory, tools, and tests before adding complexity |
| 2 | **Nocturnal agent** | Daily synthesis of sessions into `MEMORY.md` |
| 3 | **Telegram bot** | `bot.py` as adapter to `core.chat_stream()`, without duplicating logic |
| 4 | **Linux + polish** | Portability, systemd, Dockerfile, setup.py |
| 5 | **Widget events to AI** | Widgets sending user actions back to the AI as injected context |
| 6 | **Memory search** | `memory_search` + `list_memories` tools for querying MEMORY.md |
| 7 | **Code execution** | `run_code` tool for safe Python execution |

## Architecture Decisions

| Decision | Chosen | Alternative |
|----------|--------|-------------|
| Runtime | Pure Python | TypeScript |
| LLM client | OpenAI SDK | httpx direct |
| Memory | Native SQLite + Markdown | sqlite-vec / external base |
| Stream | Sync generator | Async complex |
| Config | `.env` + Markdown | Large YAML |
| Tools | `importlib` auto-registry | Manual registration |
| Frontend | Vanilla JS | React / Vue / Svelte |
| Serialization | NDJSON | SSE |
| Growth | Channels as adapters | Heavy gateway from day one |

## Guiding Principle

Kairos must grow from real utility, not from imitation. First it has to be a reliable helper for the user and for its own code; then it can add channels, automations, and external capabilities without losing readability.
