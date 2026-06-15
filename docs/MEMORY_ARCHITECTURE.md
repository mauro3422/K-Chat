# Memory Architecture (v0.0.57+)

> Sistema de memoria de 3 capas: texto plano curado, base estructurada sincronizable, y sesiones locales.

```
┌────────────────────────────────────────────────────────────────────┐
│                        CAPA 1: CONSCIENCIA                        │
│                         MEMORY.md (texto)                         │
│                                                                    │
│  Rol:      Source of truth. Identidad del agente.                 │
│  Tamaño:   ~50 KB hoy (inyectado completo en system prompt)      │
│  Futuro:   Índice rotativo + datos calientes inyectados           │
│  Sync:     ✅ Syncthing (texto plano = sin riesgo de corrupción)  │
│  Contenido: datos del usuario, bugs, checkpoints, arquitectura,   │
│             visión del proyecto, widgets, preferencias            │
│                                                                    │
│  📝 Se edita con: save_memory(key, value)                         │
│  📖 Se inyecta en: system prompt (builder.py → context)           │
│                                                                    │
├────────────────────────────────────────────────────────────────────┤
│                      CAPA 2: MEMORIA ESTRUCTURADA                  │
│                          memory.db (SQLite)                        │
│                                                                    │
│  Rol:      Índice programático. Búsqueda semántica. Grafos.       │
│  Tamaño:   Pequeño hoy (solo memory_index table)                  │
│  Futuro:   + embeddings (sqlite-vec) + knowledge_graph            │
│  Sync:     ✅ Syncthing (reconstruible desde MEMORY.md si conflicto)│
│  Tablas:                                                          │
│    • memory_index  → key-value global (sin session_id)           │
│    • (futuro) embeddings → vectores para búsqueda semántica       │
│    • (futuro) knowledge_graph → relaciones entre conceptos        │
│                                                                    │
│  📝 Se escribe con: save_memory() → MEMORY.md + memory.db         │
│  📖 Se consulta con: memory_search(), list_memories()             │
│  🔮 Futuro: inyección inteligente pre-respuesta                   │
│                                                                    │
├────────────────────────────────────────────────────────────────────┤
│                    CAPA 3: SESIONES LOCALES                        │
│                        sessions.db (SQLite)                        │
│                                                                    │
│  Rol:      Memoria episódica. Conversaciones crudas.              │
│  Tamaño:   Variable (mensajes, tools, widgets)                    │
│  Sync:     ❌ NO (cada dispositivo tiene las suyas)                │
│  Tablas:                                                          │
│    • sessions      → metadatos de sesiones                        │
│    • messages      → mensajes del chat                            │
│    • tool_calls    → historial de tools ejecutadas                │
│    • saved_widgets → widgets guardados                            │
│    • widget_states → estado de widgets                            │
│    • widget_versions → versionado de widgets                      │
│    • debug_info    → información de debug                         │
│    • gateway_log   → log del gateway                              │
│    • chat_journal  → resumen de turns                             │
│    • memory_index  → (viejo, session-scoped, legacy)              │
│                                                                    │
│  📝 Se escribe con: cada mensaje, tool call, widget save          │
│  📖 Se consulta con: db_query(), get_tool_history()               │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## Flujo de escritura

```
save_memory(key="user:nombre", value="Mauro")
  │
  ├─✍️ 1. MEMORY.md (sincrónico, bajo lock)
  │     Lee → parsea → modifica → reescribe archivo completo
  │     Invalida cache de contexto para próximo mensaje
  │
  ├─✍️ 2. memory_db.memory_index (asíncrono)
  │     INSERT OR REPLACE con key como PK
  │     Si value="" → DELETE en lugar de upsert
  │
  └─✅ Ambos exitosos → "[OK] saved key '...' in MEMORY.md."
```

## Flujo de lectura

```
Inicio de sesión:
  1. MEMORY.md se inyecta completo en system prompt
     → Sé quién sos, qué hicimos, qué proyectos tenés

Durante la conversación:
  2. Si necesito un recuerdo específico → memory_search(query)
     → Consulta memory.db por LIKE en key/value

  3. Si necesito datos de sesiones → db_query(table, ...)
     → Consulta sessions.db local

Futuro — inyección inteligente:
  4. Antes de responder, sistema consulta memory.db por
     tópicos relevantes a la conversación actual
     → Inyecta solo los recuerdos pertinentes en contexto
```

## Estrategia de sync (multi-dispositivo)

```
PC (escritorio)                      Laptop (facultad)
   │                                      │
   │  MEMORY.md ────── Syncthing ──────▶  │  (texto = sync seguro)
   │  memory.db  ────── Syncthing ──────▶  │  (binario = riesgo conflicto)
   │                                       │
   │  sessions.db (local)                  │  sessions.db (local)
   │                                       │
   Si hay conflicto en memory.db:
     1. Syncthing deja memory.db.conflicto
     2. Al arrancar server: detecta conflicto
     3. Reconstruye memory.db desde MEMORY.md
     4. MEMORY.md intacto por ser texto plano
```

## Crecimiento futuro

```
   MEMORY.md crece...                          memory.db crece...
   │                                            │
   ▼                                            ▼
  Algoritmo de poda:                          + embeddings (sqlite-vec)
  • Mantener entradas recientes               + knowledge_graph
  • Mantener entradas frecuentes              + entity_index
  • Archive a memory.db lo antiguo            + session_miner (extrae insights)
  • Inyectar solo lo relevante                + cross_session_tracer
```

## Principios

1. **MEMORY.md es el source of truth.** Siempre. memory.db es reconstruible.
2. **No hay duplicación funcional** — cada capa tiene un propósito distinto (consciencia vs búsqueda vs almacenamiento crudo).
3. **La sincronización se resuelve por capas** — texto se sincroniza siempre, binario se reconstruye si hay conflicto.
4. **Las sesiones son locales** — no necesitás los chats de la otra máquina para que Kairos te conozca.
