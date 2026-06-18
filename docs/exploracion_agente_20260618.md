# Exploración de Agente — 2026-06-18

## Estado real de FASE 2, 3 y 6 del roadmap de memoria

> Generado por agente de exploración autónomo.
> Fuentes: MEMORY_ROADMAP.md, código fuente en src/, tests/.

---

## FASE 2 — Entity Graph: **98% COMPLETA**

### Implementado
| Componente | Archivo | Estado |
|-----------|---------|--------|
| Entity extractor con léxico + patterns + aprendizaje | `src/memory/entity/extractor.py` (262L) | ✅ |
| Entity linker con grafo en memoria + flush a DB | `src/memory/entity/linker.py` (494L) | ✅ |
| search_entities() + explore_graph() | `src/memory/entity/linker.py` | ✅ |
| Migraciones 004-009 en memory.db | `src/memory/memory_schema.py` | ✅ |
| EntityRepository (upsert, CTE, search) | `src/memory/repos_memory/entity_repo.py` | ✅ |
| Tool search_entities | `src/tools/search_entities.py` | ✅ |
| Tool explore_graph | `src/tools/explore_graph.py` | ✅ |
| Integración en vectorize_sessions.py | extracción + linking + flush | ✅ |
| Tests de repos (30), explore_graph (10), search_entities (8) | — | ✅ |

### No implementado
| Componente | Impacto |
|-----------|---------|
| Tests unitarios dedicados para `extractor.py` | Bajo — funcionalidad cubierta por tests de integración |

---

## FASE 3 — Hybrid Retrieval: **100% IMPLEMENTADA**

### Implementado
| Componente | Archivo | Estado |
|-----------|---------|--------|
| HybridRetriever (3 señales en paralelo) | `src/memory/retrieval/hybrid_retriever.py` (272L) | ✅ |
| Keyword search (TF-IDF) | `src/memory/retrieval/keyword_search.py` (85L) | ✅ |
| Entity search (directo + grafo) | `src/memory/retrieval/entity_search.py` (121L) | ✅ |
| Fusion (RRF + WeightedSum) | `src/memory/retrieval/fusion.py` (109L) | ✅ |
| Reranker cross-encoder ONNX | `src/memory/retrieval/reranker.py` (126L) | ✅ |
| Token budget (greedy selection) | `src/memory/retrieval/token_budget.py` | ✅ |
| Hydrator + Tracker | `src/memory/retrieval/hydrator.py` (37L), `tracker.py` (36L) | ✅ |
| RetrievalService (auto-retrieval con throttle) | `src/core/services/retrieval_service.py` (144L) | ✅ |
| Auto-inyección en system prompt | `src/context/builder.py` | ✅ |
| recall_memories tool | `src/tools/recall_memories.py` (145L) | ✅ |

### Tests existentes
| Archivo | Tests |
|---------|-------|
| `tests/unit/memory/retrieval/test_fusion.py` | 9 tests (RRF, WeightedSum, normalize) |

### Tests faltantes
| Área | Prioridad |
|------|-----------|
| hybrid_retriever.py | Alta |
| keyword_search.py | Media |
| entity_search.py | Media |
| hydrator.py | Baja |
| tracker.py | Baja |
| token_budget.py | Media |
| reranker.py | Media |
| Integración flujo completo | Alta |

---

## FASE 6 — Memory Cells: **~85% COMPLETA**

### Implementado
| Componente | Archivo | Estado |
|-----------|---------|--------|
| Conductor curate_all() con 5 pasos | `src/memory/curator/curate.py` | ✅ |
| Gardener (8 acciones: poda, merge, cleanup) | `src/memory/curator/gardener.py` | ✅ |
| Tracer (3 detectores cross-session) | `src/memory/curator/tracer.py` | ✅ |
| Daily Synthesis (reporte Markdown) | `src/memory/synthesis/daily.py` (257L) | ✅ |
| Systemd timer + service | `.kairos/k-chat-curator.{timer,service}` | ✅ |
| Entry point CLI | `.kairos/curator.py` | ✅ |
| Session Miner (integrado en curate_all()) | `src/memory/curator/curate.py:183` | ⚠️ No es módulo independiente |
| Orchestrator (secuencial) | `curate_all()` | ⚠️ No es paralelo |

### No implementado / Mejorable
| Componente | Detalle |
|-----------|---------|
| Session Miner como módulo independiente | Extraer `curate_sessions()` a `miner.py` |
| Orchestrator paralelo | Lanzar células en paralelo con manejo de errores |
| Entity Extractor como célula background | Hoy corre inline en vectorize_sessions.py |

---

## Resumen general

| Fase | Según roadmap | Real |
|------|--------------|------|
| FASE 2 — Entity Graph | "Semana 1 — próxima" | **98%** (solo faltan tests de extractor) |
| FASE 3 — Hybrid Retrieval | "Semana 2-3" | **100% implementado** (faltan tests) |
| FASE 6 — Memory Cells | "Semana 4" | **~85%** (orquestación secuencial, no paralela) |
