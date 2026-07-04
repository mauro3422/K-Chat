# Curadores Híbridos: Pre-procesamiento Inteligente para Retrieval

Fecha: 2026-07-04
Tags: retrieval, curadores, embeddings, facetas, híbrido

## Problema

El retrieval actual es unidimensional: query → vectores → fragmentos crudos. No entiende
*qué tipo* de respuesta necesita el usuario ni conecta información de distintas facetas
(técnica, personal, proyecto, bug, histórica).

## Solución Propuesta

Que los curadores nocturnos (que ya corren con DeepSeek V4 Flash) hagan trabajo extra
de pre-clasificación y síntesis sobre los datos antes de que el retrieval los toque.

Así el LLM principal recibe contexto ya estructurado, no fragmentos planos.

## Ideas Concretas

### 1. Preguntas Sintéticas
Por cada fragmento curado (exchange de sesión o entrada de MEMORY.md), el curador
genera 2-3 preguntas que ese fragmento responde.

```
Fragmento: "Mauro prefiere comida salada, pizza y empanadas"
Preguntas:
  - "¿Qué le gusta comer a Mauro?"
  - "¿Cuál es la comida favorita de Mauro?"
  - "¿Prefiere comida dulce o salada Mauro?"
```

Esas preguntas se vectorizan y se linkean al fragmento original. Cuando el usuario
pregunta "cómo hago X", el matcheo semántico encuentra la pregunta sintética aunque
la redacción sea totalmente distinta al contenido original.

### 2. Etiquetado por Faceta
Cada fragmento recibe tags de categoría:

- `técnico` — código, arquitectura, herramientas
- `personal` — preferencias, datos del usuario
- `proyecto` — estado de proyectos, decisiones
- `bug` — bugs detectados, fixes aplicados
- `histórico` — checkpoints, hitos emocionales
- `decisión` — decisiones arquitectónicas documentadas

El retrieval filtra por faceta según la intención de la query.

### 3. Granularidad de Source
Actualmente `source` es solo `memory` o `session`. Expandir a:
- `memory:user`, `memory:bug`, `memory:decision`
- `session:debug`, `session:design`, `session:planning`, `session:casual`

Esto permite que el retrieval pesado distinto según la fuente.

### 4. Embeddings de Preguntas
No solo vectorizar el contenido, sino también las preguntas que ese contenido
responde. Esto expande el espacio de búsqueda y mejora el recall semántico.

### 5. Síntesis como Contexto
Los resúmenes diarios que ya genera el curador (`memory/synthesis/`).
Deberían integrarse al retrieval como "respuestas semi-sintetizadas".
Si la pregunta del usuario matchea con una síntesis diaria, el LLM recibe
ese resumen + los fragmentos originales para refinar.

### 6. Pesos de Importancia (Neuronas de Memoria)

Idea clave de Mauro: **no todos los vectores son iguales**. Así como las neuronas
tienen distinto potencial de activación, cada fragmento de memoria puede tener un
**peso de importancia** que se calcula matemáticamente desde metadata y se expone
al LLM para que calibre cuánto confiar en cada recuerdo.

#### Factores de peso (se combinan en una fórmula):

| Factor | Qué mide | Cómo se calcula |
|--------|----------|-----------------|
| **Recencia (R)** | Qué tan reciente es | `exp(-λ * días_desde_creación)` — decaimiento exponencial |
| **Frecuencia (F)** | Cuántas veces se accedió | `log(1 + n_accesos)` — saturación logarítmica |
| **Conexiones (C)** | A cuántas entidades linkea | `sqrt(n_entidades_asociadas)` — peso de red |
| **Confianza (T)** | Qué tan confiable es la fuente | Curador score (0.0-1.0), manual override |
| **Feedback (U)** | Interacción del usuario | Si el usuario confirmó/usó → boost |

#### Fórmula de activación (como neurona):

```
peso_total = α·R + β·F + γ·C + δ·T + ε·U
```

Cada α, β, γ, δ, ε son coeficientes tuneables. Esto produce un **peso vivo**
que cambia con el uso — memorias importantes se fortalecen, las obsolete se
atrofian (como poda sináptica).

#### Exposición al LLM

Cada fragmento retrieved se pasa al LLM CON su peso y sus factores:
```
[92%|rel:0.85|peso:0.74|recencia:0.9|frecuencia:0.6|conexiones:0.8]
"El usuario prefiere comida salada..."
```

Así el LLM sabe si es un dato reciente muy confirmado (peso alto → tomalo como
hecho) vs algo viejo con poca frecuencia (peso bajo → usalo con pinzas).

#### Hebbian Learning (opcional)

Si dos memorias se recuperan JUNTAS frecuentemente, su peso de conexión aumenta
("neurons that fire together, wire together"). Esto permite que el sistema
aprenda asociaciones naturalmente: si Mauro siempre pregunta de embeddings
después de hablar de curadores, esas dos memorias se empiezan a recuperar juntas.

---

## Arquitectura Propuesta

### Flujo completo (pre-procesamiento nocturno + retrieval en vivo)

**De noche (curador):**
1. Tomá sesiones nuevas + MEMORY.md
2. Extraé fragmentos, entidades, relaciones (ya se hace)
3. **NUEVO**: Generá preguntas sintéticas por fragmento
4. **NUEVO**: Etiquetá por faceta
5. **NUEVO**: Calculá pesos iniciales (recencia, confianza, conexiones)
6. Guardá todo en vec_meta (con nuevas columnas de metadatos)

**En vivo (retrieval):**
1. Usuario hace una query
2. Sistema detecta faceta de la query
3. Busca en vectores + preguntas sintéticas + entidades
4. Calcula peso_total para cada resultado (recencia + frecuencia + conexiones)
5. Ranking final: `(similitud_semántica * 0.6) + (peso_total * 0.4)`
6. LLM recibe fragmentos con pesos y metadata visibles

### Schema tentativo (columnas nuevas en vec_meta)

```sql
ALTER TABLE vec_meta ADD COLUMN faceta TEXT DEFAULT '';
ALTER TABLE vec_meta ADD COLUMN pregunta_sintetica TEXT DEFAULT '';
ALTER TABLE vec_meta ADD COLUMN peso_recencia REAL DEFAULT 1.0;
ALTER TABLE vec_meta ADD COLUMN peso_frecuencia REAL DEFAULT 1.0;
ALTER TABLE vec_meta ADD COLUMN peso_conexiones REAL DEFAULT 0.5;
ALTER TABLE vec_meta ADD COLUMN peso_confianza REAL DEFAULT 0.7;
ALTER TABLE vec_meta ADD COLUMN n_accesos INTEGER DEFAULT 0;
ALTER TABLE vec_meta ADD COLUMN ultimo_acceso TEXT DEFAULT '';
```

- **No necesita otro LLM** — el mismo curador nocturno hace este trabajo
- **Es aditivo** — no rompe nada existente, agrega capas
- **Aprovecha infraestructura actual** — el grafo de entidades + curadores ya corren
- **Escalable** — cada nueva fuente de datos recibe el mismo tratamiento

---

## 7. Sistema de Triggers + Activación por Grafos

Idea central de Mauro: **los triggers no son un sistema aparte — ya existen en el grafo.**

El sistema actual ya tiene:
- `entities` → nodos (palabras, conceptos)
- `entity_relations` → aristas con peso (`weight`)
- `topic_clusters` → agrupaciones semánticas
- `exchange_clusters` → fragmentos asociados por keywords compartidas

Eso **YA es la base matemática** para un sistema de atención sobre la memoria.

### ¿Cómo funciona?

**Cada fragmento curado se asocia a nodos del grafo** (entidades). Cuando un trigger
se activa (match semántico con una oración), la **activación se propaga** por las
aristas del grafo:

```
Trigger: "preguntas sintéticas"
  → matchea entidad "preguntas_sintéticas" (peso 1.0)
  → arista → "curadores_nocturnos" (peso 0.8)
  → arista → "embeddings" (peso 0.6)
  → arista → "memoria_viva" (peso 0.4)
  
  Cada entidad linkea a fragmentos de memoria.
  Activación = peso_del_trigger * peso_de_arista
  Se devuelven fragmentos con activación > umbral.
```

Esto es matemáticamente **PageRank sobre el grafo de memoria** — pero en vez de
links de página web, son conexiones semánticas entre conceptos.

### Clasificación de tokens/oraciones con metadatos

Para que esto funcione bien, cada oración/fragmento necesita metadatos de
importancia. Dos caminos complementarios:

**Por algoritmo (automático):**
- Frecuencia de términos (TF-IDF sobre el corpus de memoria)
- Centralidad en el grafo (PageRank, betweenness centrality)
- Co-ocurrencia con la query (BM25, solapamiento de entidades)
- Densidad semántica (qué tan cerca está de otros conceptos en el vector space)

**Por curador nocturno (semántico):**
- Cuando el algoritmo no alcanza, el nocturno clasifica:
  - "Este fragmento es importante porque resume una decisión clave"
  - "Este es un dato personal recurrente"
  - "Este es un bug ya fixeado — prioridad baja"
- El nocturno ya tiene contexto (MEMORY.md + sesiones) para juzgar.

### Arquitectura de Atención de Memoria

```
                     ┌──────────────────────┐
                     │    QUERY DEL USUARIO   │
                     └──────────┬───────────┘
                                ▼
                     ┌──────────────────────┐
                     │  Detección de faceta  │
                     │  + extracción de      │
                     │  entidades clave      │
                     └──────────┬───────────┘
                                ▼
              ┌─────────────────────────────────┐
              │    BÚSQUEDA EN MÚLTIPLES CAPAS   │
              │                                   │
              │  1. Vectores semánticos (oración) │
              │  2. Triggers livianos (oración)   │
              │  3. Entidades del grafo (nodos)   │
              │  4. Preguntas sintéticas          │
              └──────────┬──────────────────────┘
                                ▼
              ┌─────────────────────────────────┐
              │    SPREADING ACTIVATION          │
              │                                   │
              │  Trigger activado → activación    │
              │  se propaga por aristas del grafo │
              │  Cada nodo alcanzado suma peso    │
              │  Se forma un "cluster de atención"│
              └──────────┬──────────────────────┘
                                ▼
              ┌─────────────────────────────────┐
              │    RANKING FINAL                  │
              │                                   │
              │  score = α·semántica              │
              │        + β·activación_grafo       │
              │        + γ·peso_importancia       │
              │        + δ·recencia               │
              └──────────┬──────────────────────┘
                                ▼
              ┌─────────────────────────────────┐
              │    LLM RECIBE FRAGMENTOS          │
              │    + códigos de acceso            │
              │    + pesos visibles              │
              │    + metadatos de importancia     │
              └─────────────────────────────────┘
```

### Códigos de Acceso (Live Retrieval)

Cada trigger/fragmento tiene un **código de acceso único** (ej: `mem:trg:a3f2`).
Cuando un trigger se activa y el LLM ve el fragmento resumido, **puede decidir
si necesita el recuerdo completo** usando una herramienta tipo:

```
recall_by_code("mem:trg:a3f2")
```

Esto mantiene el contexto limpio — no se inyecta el recuerdo completo a menos
que sea relevante. El LLM decide.

---

## 8. Célula de Mantenimiento de Memoria (Anti-Alzheimer)

Mauro lo dijo claramente: mantener la coherencia de todos los recuerdos entre sí
es **difícil**. Por eso existe el Alzheimer — el cerebro gasta mucha energía en
mantenimiento de memoria.

**Problema:**
- El curador nocturno agrega memoria nueva
- Los triggers se activan y fortalecen conexiones
- Pero con el tiempo, recuerdos se vuelven contradictorios, obsoletos o duplicados
- Sin mantenimiento, el sistema pierde coherencia

**Solución propuesta — Célula "Guardián":**
- Corre semanalmente (no diario, es pesada)
- Compara todos los fragmentos curados entre sí:
  - **Duplicados** → merge (fusión de metadatos)
  - **Contradicciones** → marca con baja confianza, alerta
  - **Obsoletos** (más de N meses sin acceso) → archivo/decaimiento
  - **Inconsistentes** con el grafo → re-clasificación
- Usa el mismo DeepSeek V4 Flash con un prompt especializado

**Matemática de mantenimiento:**
- Para cada par de fragmentos: `conflicto_score = similitud_semántica * (1 - consistencia_lógica)`
- Si `conflicto_score > umbral` → marcar para revisión
- Si dos fragmentos dicen lo mismo → merge automático (sumar pesos, preservar el más reciente)

---

## 9. Hoja de Ruta Técnica (lo que sigue)

### Fase 1 — Fundación (ahora)
- [x] Entity graph con relaciones pesadas
- [x] Clustering semántico de fragmentos
- [x] Embeddings por fragmento (oración)
- [x] Sistema de curadores nocturnos

### Fase 2 — Triggers + Activación (próximo)
- [ ] Generar triggers (oraciones embebidas chicas) por fragmento curado
- [ ] Asociar triggers a nodos del grafo existente
- [ ] Implementar spreading activation sobre el grafo
- [ ] Códigos de acceso + tool `recall_by_code`
- [ ] Metadata de importancia (pesos iniciales)

### Fase 3 — Atención + Pesos Vivos
- [ ] Tracking de frecuencia de acceso a cada fragmento
- [ ] Decaimiento temporal de recencia
- [ ] Ranking fusionado (semántica + activación + peso)
- [ ] Hebbian learning (conexiones que se refuerzan con el uso)

### Fase 4 — Mantenimiento (Guardián)
- [ ] Célula de consistencia semanal
- [ ] Merge automático de duplicados
- [ ] Sistema de alerta de contradicciones
- [ ] Poda de memoria obsoleta con umbrales configurables

---

## Pendiente Inmediato

- ¿Nuevas tablas en memory.db para triggers? `triggers` (id, fragmento, entities_ids, embedding_blob, codigo_acceso, metadata)
- ¿O reutilizar vec_meta con nuevas columnas? (menos migración, más simple)
- Cómo integrar spreading activation en el HybridRetriever actual
- Qué umbrales usar para el decaimiento de recencia (días, accesos mínimos)
