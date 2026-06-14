# .kairos/ — Internal K-Chat Infrastructure

This directory contains the **self-healing infrastructure** for K-Chat:

| File | Purpose |
|------|---------|
| `watchdog.py` | Health-check daemon: monitors the web server, captures crash context, restarts on failure |
| `error_context.md` | Written by watchdog after a crash. Read by `src/context/builder.py` on next boot — lets Kairos know what went wrong |
| `k-chat.service` | Systemd user service for the main web server (`uvicorn`) |
| `k-chat-watchdog.service` | Systemd user service for the watchdog daemon |
| `k-chat-telegram.service` | Systemd user service for the Telegram bot channel |

## Architecture

```
systemd ── k-chat.service ──→ uvicorn (FastAPI web server)
         │
         └── k-chat-watchdog.service ──→ watchdog.py
         │                                  │
         │                                  ├── HTTP health check every 5s
         │                                  ├── On crash: capture diff → error_context.md
         │                                  └── Restart k-chat.service via systemd
         │
         └── k-chat-telegram.service ──→ python -m channels.telegram
                                              │
                                              └── Polls Telegram API → src.core.orchestrator
```

## Self-Healing Flow

1. Kairos edits a file (write_file / edit_file)
2. If the edit has a syntax error → **server crashes**
3. Watchdog detects the crash → captures `git diff` + last commits
4. Writes `.kairos/error_context.md` with full context
5. Restarts the server via systemd
6. On restart, `src/context/builder.py` reads `error_context.md`
7. Kairos sees the error in the **next system prompt** and fixes it

## Installation

```bash
# Install all services
cp .kairos/k-chat.service .kairos/k-chat-watchdog.service \
   .kairos/k-chat-telegram.service ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable k-chat k-chat-watchdog k-chat-telegram
systemctl --user start k-chat
```
