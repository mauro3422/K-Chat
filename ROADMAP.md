# K-Chat Memory Pipeline — Roadmap

## ✅ Completed (this session)

### Mathematical Heuristics Pipeline (LLM-free extractive scoring)
- **TF-IDF / BM25** — term scoring by corpus rarity
- **Entity Graph PageRank** — 53 entities, centrality scores [0,1]
- **PMI Clustering** — cross-document term cohesion
- **TextRank** — intra-session word-graph PageRank (window=5)
- **LSA (SVD-based)** — cross-role topic coherence with adaptive reliability
- **Cross-turn PMI** — user↔assistant term pair strength
- **Blended Coherence** — algebraic blend: `(LSA_rel·LSA + PMI_rel·PMI) / (LSA_rel+PMI_rel)`
- **Adaptive Candidate Confidence** — `base + Σ(weight_i · reliability_i · signal_i)`
- **Statistical Thresholds** — `mean ± σ` → `hold/review/auto_promote` decisions

### Infrastructure Fixes
- **sqlite-vec loading** — cached connection + `sqlite_vec.loadable_path()` discovery (works in Docker/venv/system Python)
- **In-memory semantic fallback** — loads vec0 before reading `vec_entries` virtual table
- **Venv injection** — `src/_venv_inject.py` + conftest for pytest
- **Code stripping** — removes ```code``` blocks and `inline code` before tokenization
- **STOP list expansion** — +50 Spanish filler, CSS tokens, infra terms

### Pipeline Artifacts (20 sessions × 6 dates)
```
memory/YYYY/MM/DD/
  session--{channel}--{id}.md          # Extractive summary + metadata (LSA, PMI, Blended)
  candidates/session_summary.jsonl     # 15 candidates with promotion_decision
  transversal.md                       # Cross-session synthesis
  daily.md                             # Morning digest
  events/curation.md                   # Pipeline curation report
```

---

## 🔜 Next: Curator Agent + A/B Benchmark

### Estado 2026-07-09

- ✅ `src/memory/curator/agent.py`: revisión por sesión, feedback persistido,
  ajuste conservador de pesos mediante scorer inyectado y callback de re-run.
- ✅ `src/memory/curator/benchmark.py`: benchmark baseline/treatment contra
  decisiones humanas con precision, recall, F1 y delta.
- ✅ Cobertura unitaria del agente y del benchmark.
- 🔜 Falta ejecutar una corrida A/B con candidatos reales etiquetados y aprobar
  manualmente los pesos resultantes.

### Curador LLM Agent
**Objetivo**: Leer candidates, dar feedback (promoted=true/false), ajustar `DEFAULT_WEIGHTS` via `scorer.set_weight()`, re-ejecutar pipeline, medir mejora.

**Archivos a crear**:
- `src/memory/curator/agent.py` — CuratorAgent con:
  - `review_candidates(path)` → carga JSONL, presenta para revisión
  - `adjust_weights(feedback)` → modifica `DEFAULT_WEIGHTS` basado en falsos positivos/negativos
  - `re_run_pipeline()` → regenera summaries con nuevos pesos
  - `benchmark(old_path, new_path)` → precision/recall/F1 vs decisiones humanas

**Interfaces**:
```python
class CuratorAgent:
    def __init__(self, scorer: CombinedScorer, candidate_path: str):
        ...

    def review_session(self, session_id: str, decision: str, notes: str = "") -> None:
        """decision ∈ {promote, reject, defer}"""

    def commit_adjustments(self) -> dict[str, float]:
        """Returns new weights, persists to config"""

    def run_benchmark(self, baseline_candidates: str, tuned_candidates: str) -> dict:
        """Compares promotion_decision vs human decisions"""
```

### A/B Benchmark Framework
- Baseline: `candidates_OLD.jsonl` (sin enhanced scoring)
- Treatment: `candidates_NEW.jsonl` (adaptive confidence + thresholds)
- Ground truth: decisiones del curador humano
- Métricas: Precision, Recall, F1, calibration curve

---

## 🔬 Future Experiments

### 1. NMF instead of SVD for LSA
**Problema**: SVD produce vectores negativos → requiere clamp, menos interpretable
**Solución**: Non-negative Matrix Factorization (NMF) — vectores ≥ 0 nativamente
**Implementación**: `sklearn.decomposition.NMF` o power-iteration NMF puro Python
**Beneficio**: topic vectors = distribuciones de probabilidad reales, sin clamp

### 2. Stress Testing
- Sesiones 500+ mensajes (rendimiento O(n²) en SVD/PMI)
- Pipeline concurrente (múltiples fechas en paralelo)
- Edge cases: solo tools, solo system, mensajes vacíos, code-heavy

### 3. Semantic Similarity Hardening
- Cache persistente de embeddings (evitar recomputar)
- Batch embedding para candidatos
- Evaluar `sqlite-vec` vs FAISS vs in-memory para >10k vectores

### 4. Cross-Session Topic Tracking
- Transversal synthesis detecta topics recurrentes
- Entity timeline: cuándo apareció, frecuencia, decay temporal
- "Topic drift" detection: cambio semántico en entidades a lo largo del tiempo

### 5. Curator Feedback Loop Automation
- Active learning: curador revisa solo candidates cerca del threshold (uncertainty sampling)
- Online weight update: Bayesian posterior sobre `DEFAULT_WEIGHTS` tras cada decisión
- A/B test continuo: shadow mode con pesos nuevos vs actuales

---

## 📋 Test Plan (Continuous)

| Test | Comando | Frecuencia |
|------|---------|------------|
| Unit tests (testmon) | `pytest --testmon -v --tb=short -o "addopts="` | Cada cambio |
| Pipeline full run | `python scripts/generate_session_summaries.py --candidates --transversal --daily-synthesis --curation-report` | Pre-commit |
| Candidate comparison | `python -c "compare(old.jsonl, new.jsonl)"` | Post-curador |
| Stress test | `python scripts/stress_test.py --sessions 100 --msgs 500` | Semanal |
| Regression check | `pytest tests/unit/test_*memory* -v` | Pre-push |

---

## 🎯 Success Metrics

| Métrica | Baseline (OLD) | Target (NEW) |
|---------|----------------|--------------|
| Candidate confidence spread | 0.75–0.83 (σ=0.023) | 0.70–0.85 (σ>0.03) |
| Auto-promote rate | 0% (no thresholds) | 5-15% |
| Noise in keywords | ~40% | <15% ✓ |
| LSA false negatives (short sessions) | 100% | <20% ✓ (blended rescata) |
| sqlite-vec availability | ~50% (fragil) | 100% ✓ (cached conn) |
| Pipeline time (20 sessions) | ~3 min | <2 min ✓ |

---

## 📁 Key Files Modified

```
src/
  _venv_inject.py                    # Venv site-packages injection
  memory/analysis/
    __init__.py
    corpus.py                        # TF-IDF, BM25, TextRank, strip_code, STOP list
    graph_analysis.py                # EntityGraph PageRank + graceful refresh()
    pmi.py                           # PMIClustering
    textrank.py                      # Intra-session TextRank
    turn_analysis.py                 # LSA (SVD) + Cross-PMI + reliability tracking
    semantic.py                      # SemanticSimilarity (vec0 cached + fallback fixed)
    scoring.py                       # CombinedScorer + adaptive confidence + thresholds
  memory/synthesis/session.py        # build_session_summary + blended + candidates + thresholds
  memory/curator/                    # agent.py + benchmark.py implementados

scripts/
  generate_session_summaries.py      # Pipeline entry point (venv auto-detect)

tests/
  conftest.py                        # ensure_venv() hook
```

---

*Última actualización: 2026-07-05*
