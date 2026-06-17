# Migración Backend → Arquitectura Lego

> **Fecha:** 2026-06-16  
> **Inspiración:** Frontend TS — 39 clases, 39 interfaces, 1 composition root, 0 singletons  
> **Objetivo:** Llevar el backend Python al mismo nivel de desacoplamiento que el frontend TS

---

## 1. Diagnóstico: Backend HOY vs Frontend TS

### Scorecard comparativo

| Dimensión | Frontend TS | Backend Python | Diferencia |
|-----------|-------------|----------------|------------|
| Clases con interfaz | **39/39 (100%)** | ~40%, protocols existen pero no 1:1 | El backend tiene protocols en repos pero las services no tienen interfaces 1:1 |
| Composition Root | ✅ `app_mock.ts` — 1 archivo, 0 lógica | ❌ Disperso: `get_repos()` en 7+ archivos, `new` inline en `chat_stream.py` | **Crítico** |
| Singletons globales | **0** | **3+**: `get_repos()`, `get_event_bus()`, `_config` | **Alto** |
| Inline `new` en lógica | **0** — todo en app_mock | **5+**: TelemetryService, HistoryService, LLMService, ToolExecutionService dentro de `build_stream_generator()` | **Alto** |
| Capas estrictas | ✅ `types/` ← `core/` ← `streaming/` ← `app_mock.ts` | 🟡 Parcial: `web/services/` importa `src.api.orchestrator` directamente | Medio |
| Event Bus desacoplado | ✅ `IEventBus` inyectado | ✅ `EventBus` con `get_event_bus()` pero es singleton global | Medio |
| Persistencia inyectada | ✅ Repos via constructor | 🟡 Hay protocolos, pero `get_repos()` es singleton | Medio |

### Problemas específicos

#### 🔴 P1: `get_repos()` — singleton global llamado desde 7+ lugares

```python
# Archivos que llaman get_repos():
web/services/chat_stream.py          # línea 90: repos = get_repos()
web/services/chat_stream.py          # línea 227: repos = get_repos()
web/services/message_persister.py    # línea 40: repos = get_repos()
web/services/message_renderer.py     # línea 21: repos = get_repos()
web/routers/chat.py                  # (indirecto via chat_stream)
web/routers/debug.py                 # (indirecto)
src/api/__init__.py                  # re-export
```

**Problema:** No podés testear `chat_stream.py` con repos mock sin parchear `get_repos()` con `unittest.mock.patch`. En el frontend TS, `SessionStore` recibe sus repos por constructor — cero patches.

#### 🔴 P2: `build_stream_generator()` crea dependencias inline

```python
def build_stream_generator(...):
    # ...
    repos = get_repos()                                      # ← singleton
    telemetry_service = TelemetryService()                    # ← new inline
    orchestrator_deps = OrchestratorDeps(
        repos=repos,
        history_service=HistoryService(repos=repos),           # ← new inline
        telemetry_service=telemetry_service,
        llm_service=LLMService(telemetry_service=telemetry_service),  # ← new inline
        tool_service=ToolExecutionService(),                   # ← new inline
        ...
    )
```

**Problema:** Si querés cambiar `HistoryService` por una versión mock, tenés que tocar este archivo. En el frontend TS, `StreamOrchestrator` recibe `sessionStore: ISessionStore` por constructor — no sabe ni le importa qué implementación es.

#### 🔴 P3: `get_event_bus()` — singleton global

```python
# web/services/event_bus.py
def get_event_bus() -> EventBus:
    """Get or create the global EventBus singleton."""
```

**Problema:** Cualquier módulo puede importar `get_event_bus()` y emitir/escuchar eventos sin control. En el frontend TS, el `EventBus` se pasa por constructor a los componentes que lo necesitan.

#### 🟡 P4: Capa web conoce implementaciones concretas del core

```python
# web/services/chat_stream.py
from src.api.orchestrator import (
    HistoryService,
    LLMService,
    ToolExecutionService,
    TelemetryService,
)
```

**Problema:** La capa web importa clases concretas del core, no interfaces. Si `HistoryService` cambia su constructor, hay que actualizar `chat_stream.py`. En el frontend TS, `streaming/StreamOrchestrator.ts` solo conoce `ISessionStore`, no `SessionStore`.

---

## 2. Estado deseado: Backend Lego

### Composition Root

```python
# web/app_factory.py — ÚNICO lugar con "new"

def create_app():
    # 1. Infraestructura
    config = load_config()
    db = create_engine(config.database_url)
    event_bus = EventBus()
    logger = setup_logger(config)

    # 2. Repositorios (con interfaz compartida)
    repos = Repositories(db)

    # 3. Servicios
    telemetry = TelemetryService(repos=repos)
    llm_service = LLMService(telemetry=telemetry)
    history_service = HistoryService(repos=repos)
    tool_service = ToolExecutionService(registry=get_tool_registry())
    retrieval_service = RetrievalService(repos=repos)

    # 4. Orchestrator
    orchestrator = ChatOrchestrator(
        repos=repos,
        llm_service=llm_service,
        history_service=history_service,
        tool_service=tool_service,
        telemetry_service=telemetry_service,
        retrieval_service=retrieval_service,
        event_bus=event_bus,
    )

    # 5. Web services (reciben dependencias, no las buscan)
    chat_stream = ChatStreamService(orchestrator=orchestrator, event_bus=event_bus)
    message_persister = MessagePersister(repos=repos)
    message_renderer = MessageRenderer(repos=repos)

    # 6. Routers (reciben servicios, no los crean)
    app = FastAPI()
    app.state.chat_stream = chat_stream
    # ...
```

### Diagrama de capas deseado

```
web/routers/   ←──  web/services/   ←──  src/api/  ←──  src/core/
   (HTTP)           (orquestación)       (fachada)      (lógica pura)
     │                   │                  │               │
     │   reciben         │   reciben        │  re-exporta    │  implementa
     │   servicios       │   interfaces     │  interfaces    │  interfaces
     ▼                   ▼                  ▼               ▼
  FastAPI             IChatStream         IOrchestrator    Orchestrator
                      IMessagePersister   ILLMService      LLMService
                      IMessageRenderer    IHistoryService  HistoryService
                                          IToolService     ToolExecutionService
                                          ITelemetry       TelemetryService

  get_repos() ❌       get_event_bus() ❌   DEFAULT_CONFIG ❌
```

### Reglas de la migración

1. **Ningún archivo fuera del composition root** hace `from src.memory.repos import ...`
2. **Ningún archivo** llama `get_repos()`, `get_event_bus()`, o accede a `DEFAULT_CONFIG`
3. **Cada servicio tiene una interfaz** (`Protocol`) que la capa web conoce, no la clase concreta
4. **Los routers reciben los servicios** por parámetro (FastAPI `Depends` o `app.state`), no los importan directamente
5. **`__init__.py`** de `src/api/` solo re-exporta interfaces, no implementaciones

---

## 3. Plan de migración por fases

### Fase 1 — Detectar y medir (~1 h)

- [x] Identificar todas las llamadas a `get_repos()` (7+ archivos)
- [x] Identificar todos los `new` inline de servicios en `chat_stream.py`
- [x] Identificar todos los imports directos de clases concretas desde la capa web
- [x] Contar cuántas services NO tienen Protocol

### Fase 2 — Crear interfaces faltantes (~2 h)

- [ ] Crear `ITelemetryService` Protocol si no existe
- [ ] Crear `ILLMService` Protocol si no existe
- [ ] Crear `IHistoryService` Protocol si no existe
- [ ] Crear `IToolExecutionService` Protocol si no existe
- [ ] Asegurar que `src/core/services/protocols.py` tenga todos los protocols
- [ ] Asegurar que `src/api/__init__.py` re-exporte los protocols, no las clases

### Fase 3 — Composition Root (~3 h)

- [ ] Crear `web/composition.py` o refactorizar `web/app_factory.py` como único lugar de `new`
- [ ] Eliminar `get_repos()` — pasar repos por constructor/parámetro a todos los consumidores
- [ ] Eliminar `get_event_bus()` — pasar event_bus por constructor
- [ ] Eliminar `DEFAULT_CONFIG` — pasar config por constructor
- [ ] Refactorizar `build_stream_generator()` para recibir servicios ya construidos
- [ ] Refactorizar `message_persister.py`, `message_renderer.py` para recibir repos por constructor

### Fase 4 — Routers limpios (~1 h)

- [ ] Cambiar routers para recibir servicios vía `app.state` o `Depends()` en vez de importar `get_repos()`
- [ ] Eliminar imports directos a `src.api.orchestrator` desde `web/services/`

### Fase 5 — Tests (~2 h)

- [ ] Verificar que los tests existentes sigan pasando
- [ ] Agregar tests que demuestren que se puede injectar un mock sin `patch`

---

## 4. Archivos afectados

### Para modificar (orden sugerido)

| # | Archivo | Cambio | Fase |
|---|---------|--------|------|
| 1 | `src/core/services/protocols.py` | Agregar protocols faltantes (si no existen) | 2 |
| 2 | `src/api/__init__.py` | Re-exportar solo interfaces + factory function | 2 |
| 3 | `src/api/repos.py` | Reemplazar `get_repos()` singleton por factory | 3 |
| 4 | `web/app_factory.py` | Composition root — crear servicios, inyectarlos | 3 |
| 5 | `web/services/chat_stream.py` | Recibir servicios por parámetro, no crearlos inline | 3 |
| 6 | `web/services/message_persister.py` | Recibir repos por constructor | 3 |
| 7 | `web/services/message_renderer.py` | Recibir repos por constructor | 3 |
| 8 | `web/services/event_bus.py` | Reemplazar singleton por instancia inyectable | 3 |
| 9 | `web/routers/chat.py` | Recibir `chat_stream` vía `app.state` | 4 |
| 10 | `web/routers/debug.py` | Recibir `debug_service` vía `app.state` | 4 |

### Para eliminar

| Archivo | Razón |
|---------|-------|
| `get_repos()` en todos los archivos | Reemplazar por inyección |
| `get_event_bus()` | Reemplazar por inyección |
| `DEFAULT_CONFIG` (si existe) | Reemplazar por parámetro de config |

---

## 5. Beneficios de la migración

| Hoy | Después |
|-----|---------|
| Testear `chat_stream` requiere `mock.patch('src.api.repos.get_repos')` | Testear `ChatStreamService` requiere pasarle un mock por constructor |
| Cambiar `HistoryService` implica modificar `chat_stream.py` | Cambiar `HistoryService` solo implica cambiar el composition root |
| 7 archivos llaman `get_repos()` → 7 lugares para mantener | 0 archivos llaman `get_repos()` |
| No sabés qué servicios usan event_bus hasta que leés el código | Todos los que usan event_bus lo reciben por constructor (visible en el tipo) |
| `__init__.py` re-exporta de todo | `__init__.py` re-exporta solo interfaces + factory |

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| **Regression silenciosa** — cambiar wiring puede romper rutas HTTP | Tests de integración por cada router |
| **Merge conflicts** — muchos archivos tocados | Hacer por fases, commitear después de cada fase |
| **Perder compatibilidad hacia atrás** — si alguien más usa `get_repos()` | Mantener `get_repos()` como deprecated que llama al composition root |
| **Tiempo estimado vs real** — puede llevar más | Fase 1 (diagnóstico) da visibilidad real del esfuerzo |

---

## 7. Prioridad

```
Urgente:  ─── Fase 2 (interfaces) + Fase 3 (composition root)
              └── Sin esto, el backend no es testeable sin mock.patch

Importante: ── Fase 4 (routers limpios)
              └── Sin esto, la web conoce demasiado del core

Deseable:  ─── Fase 5 (tests)
              └── Verificar que la migración funciona
```

**Tiempo total estimado: 8-10 h** distribuidas en 5 fases. No bloquea el frontend TS — se puede hacer en paralelo.
