# Curator Quality Test — 2026-07-09

## Contexto

Test completo del pipeline de extracción LLM del curador sobre 20 sesiones históricas.
Se aplicaron fixes críticos para que funcione:

| Fix | Detalle |
|-----|---------|
| `max_tokens` 1024→16384 | Modelos con razonamiento (deepseek) consumían todos los tokens en chain-of-thought |
| `PRIORITY_MODELS` + fallback | `deepseek-v4-flash-free` (Zen) como backup si Go API falla |
| `MODEL_FAIL_TTL` 300→60s | Timeouts ya no bloquean 5 minutos |
| `_switch_model` try-except | Si único modelo falla, usa FALLBACK_MODEL en vez de crashear |
| `.kairos/curator.py` import fix | `_save_memory_local` → `_save_memory_inbox_local` |
| `CURRENT DATE` en system prompt | El LLM ahora recibe `CURRENT DATE: 2026-07-09 HH:MM` → no alucina años |

## Resultados

**14 de 20 sesiones produjeron extracciones (~50 entradas totales).**

### Bugs detectados (alta precisión)

- `bug:get-tool-history-async-error` — llama a async sin await, coroutine se pierde
- `bug:extract_text_tool_missing_return` — construye `final` pero no lo retorna, return prematuro
- `bug:db_query-column-validation` — usaba `parent_db` en vez de `source_db`
- `bug:memtool-delete-empty-value-fails` — value="" tratado como parámetro faltante
- `bug:duplicacion-mensajes` — detectado durante pruebas
- `bug:write_file-failure` — fallos esporádicos
- `bug:respuestas-no-recibidas-hasta-reinicio` — delivery de respuestas cortado
- `bug:chat_input_lock_on_session_change` — input.disabled no se resetea
- `bug:ts-frontend-sse-disconnect` — frontend TS no conectado a DB/SSE/Telegram
- `bug:interpretacion_temporal_incorrecta` — asistente fabrica narrativas temporales sin verificar timestamps

### Decisiones y arquitectura

- `decision:inyeccion-automatica-hasta-umbral` — mantener inyección hasta superar umbral de sesiones
- `decision:formalizar_io_recuerdos` — formalizar entrada/salida de recuerdos
- `decision:documentar-ideas-embeddings` — doc de búsqueda semántica avanzada
- `decision:permiso-explorar-sistema-y-docs` — Mauro autoriza explorar docs del sistema
- `decision:desarrollar-habilidad-svg` — sistema de generación SVG con run_code + Bézier
- `decision:memory-cleanup-delegated-to-ai` — limpieza delegada al asistente
- `decision:chatgpt-plus-mcp-bridge` — usar ChatGPT Plus como recurso vía MCP

### Proyecto y visión

- `proyecto:vision-memoria-viva-inyecciones-entre-razonamientos` — memoria "viva" con inyecciones mid-reasoning
- `proyecto:curator-pipeline-tecnica` — pipeline TF-IDF + clustering + curador LLM
- `proyecto:parche-curacion-grafos` — parche con grafos en otra PC
- `proyecto:geckairos-mascota` — gecko chibi cyberpunk, SVG con Bézier
- `proyecto:lan-multi-device` — sesiones federadas, peer diagnostics, failover
- `proyecto:sse-multi-dispositivo` — notificación a todos los dispositivos
- `proyecto:two-pc-lan-checklist` — validación sync entre PCs
- `proyecto:mejora-recuperacion-indexada` — índices, umbrales, resúmenes selectivos
- `proyecto:backup-emergencia-dos-frentes` — MEMORY.md + DBs
- `proyecto:plan-fix-async` — fases de corrección async

### Info personal

- `user:examenes-julio-2026-07-03` — Matemáticas aprobado, Base de Datos regular, Taller pendiente, 3 TPs

### Ideas del usuario

- `idea:inyeccion-mid-reasoning` — inyectar memorias durante razonamiento del asistente
- `idea:semantic-embeddings-as-triggers` — embeddings como activadores semánticos
- `idea:curators-generate-tags` — curadores generen etiquetas y preguntas
- `idea:meta-data-weights` — pesos a metadatos para vectores
- `decision:pesos-sinapticos-memoria` — memorias como pesos sinápticos artificiales

## Calidad

| Aspecto | Valoración |
|---------|-----------|
| Precisión de bugs | ⭐⭐⭐⭐⭐ Excelente — raíz exacta, código referenciado |
| Decisiones capturadas | ⭐⭐⭐⭐ Muy buena — contexto y razón |
| Visión de producto | ⭐⭐⭐⭐ Muy buena — captura la intención del usuario |
| Fechas | ⭐⭐⭐⭐⭐ Correctas — fix de CURRENT DATE funciona |
| Redundancia | ⚠️ Mismo bug sale de 3+ sesiones — falta dedup semántico |
| Entradas triviales | ⚠️ `user:name → Mauro` no aporta valor |
| Estabilidad API | ⚠️ ~15% de timeouts (OpenCode Go micro-cortes) |

## Cómo repetir

```bash
cd /home/maurol/dev/K-Chat
source venv/bin/activate

# Limpiar catálogo para forzar re-procesamiento
sqlite3 memory/kairos_curated_memory.db \
  "DELETE FROM memory_processing_catalog WHERE stage='curated';"

# Correr curator completo (usar venv python!)
python -m src.memory.curator.curate

# Solo LLM extraction (sin gardener/tracer/vectorize)
python -c "
import asyncio
from src.memory.curator.curate import curate_clusters, curate_sessions
async def run():
    c = await curate_clusters(dry=False)
    s = await curate_sessions(days=30, dry=False)
    print(f'Clusters: {len(c)}, Sessions: {len(s)}')
    for e in c + s:
        print(f'[{e[\"key\"]}] {e[\"value\"][:150]}')
asyncio.run(run())
"

# Entry point nocturno (systemd timer)
python .kairos/curator.py
```

## Archivos relevantes

- Resultados detallados: `docs/curator-quality-test-2026-07-09.md` (este archivo)
- Pipeline principal: `src/memory/curator/curate.py`
- Entry point nocturno: `.kairos/curator.py`
- Síntesis diaria: `memory/YYYY/MM/DD/daily.md`
- DB curada: `memory/kairos_curated_memory.db`
