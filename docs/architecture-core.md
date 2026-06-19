ARQUITECTURA DE src/core/ — K-Chat
===================================

1. QUÉ HACE CADA ARCHIVO
--------------------------
__init__.py        — Punto de entrada: exporta chat() y chat_stream().
_deps.py           — Removed historical seam; runtime uses direct imports.
orchestrator.py    — Orquestador principal: gestiona historial, compressión y delega al tool loop.
tool_loop.py       — Bucle de ejecución de herramientas: LLM → tool calls → ejecutar → repetir (turnos compartidos).
history_parser.py  — Parsea filas de BD a dicts de mensajes OpenAI.
history_rebuilder.py — Reconstruye historial completo desde BD (repo + parser + system prompt).
history_ui.py      — Filtra mensajes para UI: oculta tool messages, conserva solo último assistant por turno.
history_parser.py  — Parsea filas de BD a dicts de mensajes OpenAI, sanitiza tool calls huérfanos.
history_rebuilder.py — Reconstruye historial completo desde BD (repo + parser + system prompt).
history_ui.py      — Filtra mensajes para UI: oculta tool messages, conserva solo último assistant por turno.


2. FLUJO DE DATOS
-------------------
Mensaje usuario → chat_stream() (orchestrator.py:47)
  → Inyecta system prompt si historial vacío
  → Append user message al historial
  → Delega a run_tool_loop_streaming() o run_tool_loop_sync() (tool_loop.py)
    → Llama a src.llm.client.chat_stream / src.llm.client.chat (con tools y reasoning)
    → Si LLM retorna tool_calls:
        → Ejecuta run_parallel_tools() (src.tools.runner)
        → Append assistant+tool_calls al historial
        → Append tool results al historial
        → Repite (max MAX_TOOL_TURNS compartidos)
    → Si LLM retorna contenido final:
        → Yield chunks al caller
        → Append assistant final al historial
  → Guarda debug info si se solicita
  → Comprime historial si compress_fn lo indica


3. DEPENDENCIAS POR ARCHIVO
-----------------------------
__init__.py     → src.llm, src.core.orchestrator
_deps.py        → removed seam; no runtime consumers
orchestrator.py → src.llm.get_default_model, src.context.build_system_prompt,
                  src.tools.runner.run_parallel_tools, src.core.tool_loop, src.llm.client, src.tools
tool_loop.py    → src.tools, src.llm.client, src.memory.repos.MessageRepository
history_parser.py  → (solo stdlib: json, datetime)
history_rebuilder.py → src.memory.repos.MessageRepository, src.context.build_system_prompt,
                       src.core.history_parser
history_ui.py      → (ninguna dependencia externa, puro stdlib)
history_parser.py → (solo stdlib: json, datetime)
history_rebuilder.py → src.memory.repos.MessageRepository, src.context.build_system_prompt,
                       src.core.history_parser
history_ui.py   → (ninguna dependencia externa, puro stdlib)


4. PUNTOS DE ACOPLAMIENTO
----------------------------
B) _deps.py ya no existe como seam activo.
B) tool_loop.py → import lazy de src.api.save_message (líneas 56, 301): acoplamiento circular implícito.
C) orchestrator.py → Parámetros compress_fn / should_compress_fn inyectados como optional callbacks,
   pero el caller debe conocer la implementación concreta.
E) history_rebuilder.py → Singleton global _repo: dificulta testing y provoca acoplamiento global.
F) history_parser.py → Acceso posicional a filas de BD (row[0], row[3], row[6]...): frágil ante cambios de esquema.
G) tool_loop.py → Constants OUTPUT_CHUNK_SIZE=12 y MAX_TOOL_TURNS=5 hardcodeadas, no configurables. El chunk size ya salió a `src/constants.py`.
H) tool_loop.py → Persistencia de assistant tool-turns todavía se hace con un repositorio module-level; convendría inyectarlo si se quiere aislar más.


5. LO QUE ESTÁ BIEN
----------------------
+ Separación clara: historial (parser/rebuilder/ui) separado del loop de ejecución.
+ El runtime ya no depende de _deps.py; la inyección quedó repartida en módulos concretos.
+ Historial sanitizado (history_parser.py:48) descarta tool calls huérfanos correctamente.
+ Filtrado UI (history_ui.py) es puro y testeable sin dependencias externas.
+ tool_loop.py usa dataclass _ToolLoopContext para encapsular estado del loop.
+ Streaming y sync paths comparten la misma interfaz de yield.
+ Debug info se acumula de forma opcional sin afectar el path normal.


6. LO QUE PODRÍA MEJORAR
---------------------------
1. Reemplazar acceso posicional por named tuples o dataclasses en history_parser.py
   para robustez ante cambios de esquema BD.
2. Convertir _repo en history_rebuilder.py a inyección de dependencia en vez de singleton global.
3. Externalizar MAX_TOOL_TURNS y OUTPUT_CHUNK_SIZE a configuración centralizada. `TOOL_OUTPUT_CHUNK_SIZE` ya quedó centralizado.
4. Crear protocolo/typing para compress_fn/should_compress_fn en vez de Callable genérico.
5. Mover save_message fuera de tool_loop.py (lazy import anti-patrón) → ya quedó resuelto usando `MessageRepository` directo.
6. history_parser/rebuilder/ui ya están separados; si hace falta más simplicidad, el siguiente paso es reducir helpers compartidos.
