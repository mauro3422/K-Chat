# .kairos/ — K-Chat Infrastructure (Lego Architecture)

This directory holds the **self-healing infrastructure** for K-Chat.
Each component is a Lego brick — independent, replaceable, testable.

| File | Lego | Purpose |
|------|------|---------|
| `watchdog.py` | 🛡️ Watchdog | Health-check daemon: monitors web server + bot, captures crash context, restarts via systemd |
| `error_context.md` | 📋 Crash Log | Written by watchdog after crash. Read by `src/context/builder.py` on boot → Kairos auto-heals |
| `k-chat.service` | 🌐 Web Server | Systemd user service for uvicorn (FastAPI on :8000) |
| `k-chat-watchdog.service` | 🛡️ Watchdog Service | Systemd user service that runs watchdog.py |
| `k-chat-telegram.service` | 🤖 Bot Service | Systemd user service for python -m channels.telegram |
| `telegram_bot.pid` | 🔒 PID Lock | Prevents duplicate bot instances (auto-cleaned si stale) |
| `telegram_offset` | 📍 Offset | Persiste el último update_id de Telegram para resumir tras reinicio |

## Lego Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     systemd (user session)                          │
│                                                                     │
│  🌐 k-chat.service           🤖 k-chat-telegram.service            │
│  Restart=always               Restart=always                        │
│  │                             │                                      │
│  ├─ uvicorn web.server:app    ├─ python -m channels.telegram        │
│  │   :8000 (0.0.0.0)          │   Polling loop con backoff           │
│  │   health: GET /health      │   PID lock + offset persistido      │
│  │                             │   Máx 10 errores → shutdown         │
│  │                             │                                      │
│  └── 🛡️ k-chat-watchdog.service                                     │
│       Restart=on-failure                                              │
│       │                                                               │
│       ├─ python .kairos/watchdog.py                                  │
│       │  Cada 5s: GET /health → 200? sigo                           │
│       │  3 fallos consecutivos → crash confirmado                    │
│       │  → Captura git diff + últimos commits                        │
│       │  → Escribe error_context.md                                  │
│       │  → systemctl restart k-chat.service                         │
│       │                                                               │
│       └── Monitoreo pasivo del bot                                   │
│           Cada ~60s verifica que el PID del bot esté vivo            │
└─────────────────────────────────────────────────────────────────────┘
```

## Autogestión de cada Lego

### 🌐 Web Server (`k-chat.service`)
- **Restart=always**: systemd lo revive siempre, incluso si fue kill -9
- **Watchdog**: si el health endpoint falla 3 veces seguidas, guarda contexto y lo reinicia
- **Bind**: `0.0.0.0:8000` para dashboards externos

### 🤖 Bot (`k-chat-telegram.service`)
- **PID Lock**: escribe `.kairos/telegram_bot.pid`. Previene duplicados chequeando `/proc/<pid>/cmdline`
- **Auto-limpieza**: si el PID lock está stale (proceso muerto o PID corrupto), lo borra solo
- **--force flag**: permite override manual (`python -m channels.telegram --force`)
- **Restart=always**: systemd lo revive siempre
- **Offset persistido**: retoma mensajes donde los dejó

### 🛡️ Watchdog (`k-chat-watchdog.service`)
- Checkea el health endpoint cada 5s
- 3 fallos consecutivos para confirmar crash (evita falsos positivos)
- Cooldown de 60s entre recuperaciones
- Captura git diff + últimos commits en `error_context.md`
- También verifica el PID del bot cada ~60s (log warning, no restart — eso lo hace systemd)

## Self-Healing Flow

1. Kairos edita un archivo (write_file / edit_file)
2. Si el edit tiene un error de sintaxis → **server crashea**
3. Watchdog detecta el crash (3 health checks fallidos)
4. Captura `git diff` + últimos commits
5. Escribe `.kairos/error_context.md` con contexto completo
6. Reinicia el server via systemd
7. En el próximo boot, `src/context/builder.py` lee `error_context.md`
8. Kairos ve el error en el **siguiente system prompt** y lo auto-corrige

## ¿Qué pasa si...?

| Escenario | Reacción |
|-----------|----------|
| Web server crashea | Watchdog lo detecta → captura contexto → systemd lo reinicia |
| Bot de Telegram crashea | systemd (Restart=always) lo reinicia al toque |
| Bot duplicado arranca | PID lock detecta el duplicado → exit(1) |
| PID lock stale (kill -9) | Se auto-limpia al arrancar la próxima vez |
| Web server recibe kill -9 | systemd lo revive (Restart=always) |
| Watchdog crashea | systemd lo revive (Restart=on-failure) |
| DB se traba | busy_timeout=5000 → error → systemd restart → WAL checkpoint |
| Se va la luz | systemd arranca todo al iniciar sesión (enabled) |

## Acoplamientos y Reglas Lego

```
src/ (core, tools, llm, memory)  ←  NO importan web/ ni channels/
web/                              ←  Importa src/ (vía src.api)
channels/                         ←  Importa src/ (vía src.api)
.kairos/                          ←  NO importa nada del proyecto (autónomo)
systemd                           ←  NO importa nada (orquestador externo)
```

- **`watchdog.py`** NO importa nada de `src/`, `web/` o `channels/`. Solo usa `urllib`, `subprocess`, `git`.
- **Los services de systemd** NO saben de la lógica interna. Solo ejecutan procesos y los mantienen vivos.
- **El PID lock** es parte del entry point del bot (`__main__.py`), no del core.
- **El offset** lo persiste el bot, no el core.

## Troubleshooting

```bash
# Ver estado de todos los servicios
systemctl --user status k-chat k-chat-telegram k-chat-watchdog

# Ver logs del watchdog
journalctl --user -u k-chat-watchdog.service -f

# Ver logs del bot
journalctl --user -u k-chat-telegram.service -f

# Ver logs del web server
journalctl --user -u k-chat.service -f

# Forzar reinicio del bot (si el PID lock está trabado)
python -m channels.telegram --force

# Forzar reinicio completo
systemctl --user restart k-chat k-chat-telegram
```
