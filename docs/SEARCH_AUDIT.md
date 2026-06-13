# Auditoría de búsqueda web / SearXNG

## 1. Qué cubre

Este bloque mezcla tres piezas:
- el tool [`src/tools/web_search.py`](/home/maurol/dev/K-Chat/src/tools/web_search.py)
- el lifecycle opcional de SearXNG en [`dependencies/manage.py`](/home/maurol/dev/K-Chat/dependencies/manage.py)
- el arranque de la app en [`web/app_factory.py`](/home/maurol/dev/K-Chat/web/app_factory.py)

## 2. Corte de responsabilidades actual

- `web_search.py` solo consulta `GET /search` en el SearXNG local y formatea resultados.
- `dependencies/manage.py` ya no intenta instalar dependencias por defecto al arrancar.
- `web/app_factory.py` puede intentar auto-start, pero un fallo de SearXNG ya no bloquea el resto de la app.

## 3. Puntaje

- Desacople del bloque de búsqueda: **7.9/10**
- Contratos y límites: **8.0/10**
- Robustez ante regresiones: **8.2/10**
- Legibilidad operativa: **7.7/10**

## 4. Lo que está bien

- `web_search.py` no maneja lifecycle de procesos.
- El tool tiene retries y formato estable de salida.
- El auto-start ya no dispara instalación implícita de dependencias.
- La app sigue arrancando aunque SearXNG no esté listo.

## 5. Riesgos que todavía quedan

| Riesgo | Impacto | Estado |
|---|---|---|
| `dependencies/manage.py` aún mezcla status, instalación opcional y arranque de proceso | Medio | Funciona, pero sigue siendo el borde más cargado |
| `web_search.py` depende de un servicio local externo | Medio | Correcto, pero frágil si SearXNG cae |
| `app_factory` acopla bootstrap de búsqueda con lifespan general | Bajo/medio | Aceptable, aunque no ideal |

## 6. Qué no romper

1. El arranque de la app no debe intentar instalar dependencias por defecto.
2. `web_search` debe degradar con error legible si SearXNG no responde.
3. El error de búsqueda no debe tumbar el chat general.
4. El contrato de `web_search` en `DEFINITION` debe seguir estable.

## 7. Regresión cubierta

- [`tests/unit/test_searxng_manage.py`](/home/maurol/dev/K-Chat/tests/unit/test_searxng_manage.py)
- Caso: si SearXNG no está instalado, `searxng_start()` devuelve error sin invocar instalación.

## 8. Siguiente corte razonable

Si se sigue puliendo este bloque, el próximo paso útil es:
1. mover el lifecycle de SearXNG a un helper explícito separado de `dependencies/manage.py`.
2. hacer que `web_search.py` use un cliente/fetcher inyectable para testear mejor timeouts y retries.
