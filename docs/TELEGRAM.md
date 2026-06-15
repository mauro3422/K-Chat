# Telegram Channel — K-Chat

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                     Telegram Bot (polling)                    │
│  channels/telegram/bot.py   ◄── get_updates() ◄── TG API    │
│         │                                                    │
│         ▼                                                    │
│  channels/telegram/adapter.py  ──► process_message()         │
│         │                                                    │
│         ▼                                                    │
│  src.core.orchestrator.chat_stream() ──► LLM + Tools + Mem   │
│         │                                                    │
│         ▼                                                    │
│  channels/telegram/renderer.py   ──► send_message() ──► TG   │
│         │                                                    │
│         ├── TelegramAPIClient    (httpx, offset persistido)  │
│         ├── MessageManager       (edición de mensajes)        │
│         ├── RateLimiter          (ley de abuso de TG)         │
│         ├── CharSplitter         (split en 4096 chars)        │
│         ├── TelegramErrorHandler (errores + retry)            │
│         └── TelegramRenderer     (stream → mensajes TG)      │
│                                                              │
│  Persistencia:                                               │
│    offset → .kairos/telegram_offset                          │
│    PID    → .kairos/telegram_bot.pid                         │
│    DB     → sesiones y mensajes en SQLite                    │
└─────────────────────────────────────────────────────────────┘
                ▲
                │ spawn (subprocess)
        ┌───────┴────────┐
        │  src/gateway.py │  ←── python -m src.gateway
        └────────────────┘
                ▲
                │ systemd --user
    ┌───────────┴────────────┐
    │ k-chat-telegram.service │
    └────────────────────────┘
```

El bot corre en **polling mode** contra la Telegram API. No usa webhooks. Cada `update_id` se persiste a disco para resumir limpiamente tras reinicios. Las sesiones se nombran `Telegram ({chat_id})` y sobreviven reinicios del bot via la DB de memoria.

## Comandos de operación

```bash
# Systemd (producción)
systemctl --user start k-chat-telegram.service
systemctl --user stop k-chat-telegram.service
systemctl --user restart k-chat-telegram.service
systemctl --user status k-chat-telegram.service

# Gateway (desarrollo — lanza bot + web + searxng)
python -m src.gateway --no-web --no-searxng

# Directo (debug — solo el bot, stderr a terminal)
python -m channels.telegram --debug
python -m channels.telegram --debug --token 123456:ABC-DEF  # override token
python -m channels.telegram --force                           # ignorar PID lock
```

## Logs

| Origen | Cómo verlo |
|--------|------------|
| Systemd journal | `journalctl --user -u k-chat-telegram.service -f` |
| Gateway stderr | `logs/telegram.log` (cuando lo levanta `gateway.py`) |
| Server logs | `logs/server/YYYY-MM-DD.jsonl` (eventos de sesión) |

## Configuration

| Variable | Requerida | Descripción |
|----------|-----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Sí | Token del bot (de BotFather) |
| `TELEGRAM_ALLOWED_USERS` | No | IDs de Telegram separados por coma. Vacío = permitir todos |
| `TELEGRAM_POLL_INTERVAL` | No | Segundos entre polls (default: `1.0`) |
| `TELEGRAM_WEBHOOK_URL` | No | Si se setea, intenta usar webhook en vez de polling |
| `LLM_MODE` | No | Modo del LLM (default: `go`) |

Todas se cargan via `channels/telegram/config.py:load_telegram_config()` desde environment o `.env`.

## Session lifecycle

1. **Creación**: cuando un usuario manda un mensaje, `adapter.py:_get_or_create_session()` busca una sesión existente llamada `Telegram ({chat_id})` en la DB. Si no existe, crea una con ID `tele_{uuid}` y la renombra.
2. **Persistencia**: mensajes user y assistant se guardan en `messages` via `repos.messages.save_record()`.
3. **Resumen**: al reiniciar el bot, la sesión se restaura desde DB incluyendo el historial de mensajes.
4. **Reset**: `/new` o `/reset` generan un nuevo `session_id` (mismo nombre `Telegram ({chat_id})`).
5. **Visibilidad en web UI**: la sesión aparece en el sidebar con un icono SVG de teléfono (`sidebar.html:10`).

## Troubleshooting

| Problema | Causa probable | Solución |
|----------|---------------|----------|
| "Connection error" en warmup | LLM provider no responde al inicio | Esperar ~5s y reintentar (no fatal, el bot sigue) |
| Bot no responde mensajes | Proceso caído | `systemctl --user status k-chat-telegram.service` |
| PID lock impide arrancar | Bot ya corriendo o PID huérfano | `rm .kairos/telegram_bot.pid` o `--force` |
| Sesiones duplicadas en web | Múltiples session_ids para mismo chat | `DELETE FROM sessions WHERE name LIKE 'Telegram%'` |
| Logs silenciosos | stderr redirigido a archivo | Revisar `logs/telegram.log` o journal |
| "Too many errors, shutting down" | 10+ errores consecutivos en el loop | Revisar journal, corregir causa, reiniciar |

## Comandos del bot

| Mensaje | Respuesta |
|---------|-----------|
| `/start` | Mensaje de bienvenida con lista de comandos |
| `/help` | Lista de comandos disponibles |
| `/new` | Reinicia la sesión (nuevo session_id) |
| `/reset` | Ídem `/new` |
| Cualquier texto | Se procesa via `chat_stream()` con tools, memoria y búsqueda web |
