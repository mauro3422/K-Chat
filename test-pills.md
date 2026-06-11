# Protocolo: Test de consistencia de pills en save_memory

## Contexto
Se detectó un bug visual: `save_memory` se ejecuta correctamente (tool history muestra `(ok)` y el dato persiste en MEMORY.md), pero la pill visual (indicador de herramienta ejecutada) NO aparece en la UI en algunos casos, aunque en otros SÍ aparece. No hay un patrón claro aún.

## Objetivo
Identificar en qué condiciones aparece o no la pill visual al ejecutar `save_memory`, para aislar la causa raíz.

## Variables a probar
1. **Posición del tool call**: al inicio del mensaje, en medio, al final
2. **Cantidad de tools**: un solo save vs múltiples saves en el mismo turno
3. **Texto narrativo**: con narración previa ("guardo esto") vs sin narración (solo tool call)
4. **Combinación con otras tools**: save_memory solo vs save_memory + otra tool

## Protocolo

### Ronda 1 — Posición
1. Sin narrar, llamá a `save_memory(key="test:posicion-1", value="test")` al INICIO de tu respuesta (antes de cualquier texto)
2. Sin narrar, llamá a `save_memory(key="test:posicion-2", value="test")` en MEDIO de tu respuesta (después de texto)
3. Sin narrar, llamá a `save_memory(key="test:posicion-3", value="test")` al FINAL de tu respuesta (como último elemento)

### Ronda 2 — Cantidad
4. Ejecutá TRES saves en paralelo: `save_memory(key="test:multi-1",...)` + `save_memory(key="test:multi-2",...)` + `save_memory(key="test:multi-3",...)`

### Ronda 3 — Narración
5. Narrá "voy a guardar esto" y LUEGO ejecutá `save_memory(key="test:narrado-1",...)`
6. Sin narrar, ejecutá directamente `save_memory(key="test:directo-1",...)`

### Ronda 4 — Combinación
7. Ejecutá `save_memory(key="test:combo-1",...)` + `get_tool_history(limit=3)` en el mismo turno

## Registro
Después de CADA ronda, usá `get_tool_history` para verificar que las tools realmente se ejecutaron. Compará con lo que ves en la UI (pills visibles).

## Output esperado del asistente
En cada ronda, el asistente debe:
- Indicar qué está probando
- Ejecutar la/las herramientas
- Mostrar el resultado
- Preguntar al usuario si vio las pills

---
Creado: 2026-06-09 | Bug: pill-inconsistente-ui | Sesión original: 2026-06-09 01:xx