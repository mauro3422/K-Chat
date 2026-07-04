# 🐞 Bugs Conocidos — K-Chat v0.2.3

Bitácora de bugs detectados para arreglar a futuro.
Formato: cada bug con síntomas, causa probable, y posible fix.

---

## 1. 🔁 Retry en Cascada / Duplicación de Mensajes

**Síntoma:** El servidor envía múltiples copias del mismo mensaje al modelo. En los logs se ven attempts mezclados (4/3, 3/3, 2/3 simultáneos) — el sistema de retry se pisa a sí mismo.

**Evidencia:** 2026-07-04 18:48-19:03 — un mismo mensaje del usuario se reintentó ~7+ veces, con retries anidados que no respetaban el límite de 3.

**Causa probable:**
- `stream_retry_handler.py` no bloquea nuevos intentos mientras uno ya está en curso
- El frontend reenvía el mensaje si no recibe respuesta rápida, y el backend lo trata como un mensaje nuevo que también reintenta
- El `Retry-After` o backoff no se respeta entre capas (frontend ↔ backend ↔ provider)

**Posible fix:**
- Implementar lock por `session_id` en el endpoint de chat: si ya hay un stream activo, rechazar o encolar
- Sincronizar contadores de retry entre frontend y backend
- Que el frontend no reintente automáticamente si ya hay un request en vuelo

---

## 2. 🧠 Error de Modelo: "model — The model encountered an error"

**Síntoma:** El provider (DeepSeek V4 Flash free, OpenCode Zen flash free) devuelve error genérico. El sistema reintenta 3 veces y finalmente falla, perdiendo el mensaje del usuario.

**Evidencia:** Ocurrió repetidamente el 2026-07-04 entre 18:48 y 19:03, justo cuando se acabó el rate limit del plan Go y se cayó al free.

**Causa probable:**
- Rate limit alcanzado + fallback al free = error en vez de degradación graceful
- El mensaje de error del provider es genérico ("The model encountered an error"), no distingue entre rate limit, timeout, o error real

**Posible fix:**
- Detectar rate limit vs error real en `src/llm/client.py` o `models.py`
- Si es rate limit, esperar y reintentar con backoff más largo (30s+)
- Mejorar logging: capturar el cuerpo de la respuesta del provider (status, headers, body) antes de tragar el error
- Considerar cola de reintentos con backoff exponencial en vez de 3 intentos seguidos

---

## 3. 🔍 SearXNG Devuelve 0 Resultados

**Síntoma:** La tool `web_search` responde "No results found." aunque SearXNG esté corriendo (HTTP 200). El buscador está vivo pero no trae nada.

**Evidencia:** 2026-07-04 — PID 297121 corriendo en :8080, responde HTTP 200, pero las búsquedas reales vuelven vacías. En stress tests de junio aparecía como "SearXNG caído".

**Causa probable:**
- `use_default_settings: true` en settings.yml activa todos los engines por defecto, pero muchos están rate-limiteados o rotos sin API keys
- `outgoing.request_timeout: 5.0` en SearXNG es muy bajo — los engines externos no responden en 5s y SearXNG devuelve página vacía
- La tool usa timeout 15s, pero SearXNG ya cortó a los 5s

**Posible fix:**
- Aumentar `outgoing.request_timeout` a 15-20s en `.config/searxng/settings.yml`
- Configurar engines específicos en vez de `use_default_settings: true` (google con rate limit, o engines más estables como duckduckgo, wikipedia, etc.)
- Mejorar manejo en `web_search.py`: diferenciar entre "SearXNG devolvió 200 con 0 resultados" vs "SearXNG está caído" vs "resultados reales"

---

## 4. 🌙 Curador Nocturno No Procesa Sesiones

**Síntoma:** El curador (curate.py via systemd timer) corre todas las noches a las 00:10 pero las síntesis muestran 0 sesiones, 0 mensajes, 0 embeddings nuevos. El `work_catalog` está vacío.

**Evidencia:** Síntesis diarias del 2026-06-28 al 2026-07-04 — todas reportan 0 sesiones procesadas. La memoria curada tiene 225 entries pero son todas de checkpoints viejos, no de conversaciones nuevas.

**Causa probable:**
- El curador apunta a una DB diferente a `kairos_memory.db` (path incorrecto)
- El `last_vectorized_idx` está en su máximo y no detecta exchanges nuevos
- Los timers systemd están configurados pero el script no se ejecuta realmente (permisos, environment, Python path)
- `work_catalog_repo.mark()` no encuentra sesiones porque la query de búsqueda está mal

**Posible fix:**
- Debuggear el timer systemd: verificar logs de `journalctl -u k-chat-curator.timer`
- Verificar qué DBs está leyendo el curador vs dónde están las sesiones reales
- Agregar logging más detallado en cada paso del curador
- Hacer un dry-run manual del curador para ver qué encuentra

---

## 5. 📋 Auto-Retrieval Muestra Siempre los Mismos Fragmentos

**Síntoma:** El sistema de auto-inyección de memoria (que corre cada mensaje) siempre trae fragmentos de las mismas sesiones viejas (884d7680, fb5fa2ff, a4b4021f). Las memorias curadas nuevas no aparecen.

**Evidencia:** Revisando las inyecciones de las últimas respuestas — siempre los mismos session_ids, mismos scores.

**Causa probable:**
- El `source_filter='session'` en `retrieval_service.py` filtra las memorias curadas (source='memory'), dejando solo sesiones crudas
- Como el curador no procesa sesiones nuevas (bug #4), siempre encuentra las mismas sesiones viejas
- Los embeddings de sesiones nuevas no se generan porque `last_vectorized_idx` no avanza

**Posible fix:**
- Debuggear el flujo: qué embeddings existen realmente en `vec_meta` vs qué sesiones hay en `messages`
- Verificar que `vectorize_session` se ejecute al cerrar sesión (hook en `chat_stream.py`)
- Una vez que el curador funcione, ajustar el threshold de retrieval para priorizar memoria curada sobre sesiones crudas

---

## 6. ⚡ Rate Limit del Provider no se Degrada Gracefully

**Síntoma:** Cuando se acaba el rate limit del modelo Go, el sistema no fallbackea suavemente al free — directamente tira error y pierde el mensaje.

**Evidencia:** 2026-07-04 — se acabó el rate limit Go y los mensajes empezaron a fallar con "model encountered an error".

**Causa probable:**
- `manager.py` o `client.py` no detectan `429` o `401 insufficient balance` como rate limit, lo tratan como error genérico
- No hay lógica de "si falla modelo A, probar modelo B automáticamente"
- El usuario tiene que cambiar manualmente de modelo

**Posible fix:**
- Detectar códigos HTTP 429 (rate limit) y 401 (insufficient balance) en `_api_call` o `process_chunks`
- En caso de rate limit, hacer switch automático al siguiente modelo disponible (free tier)
- Notificar al usuario: "Se acabó la cuota del modelo Go, cambié a Flash Free automáticamente"

---

## 📝 Notas Adicionales

- Muchos de estos bugs están interconectados: el #2 (model error) desencadena el #1 (retry cascade), y el #4 (curator) causa el #5 (stale retrieval)
- La prioridad sugerida sería: **#2/#6 (rate limit graceful)** → **#1 (retry cascade)** → **#4 (curator)** → **#5 (retrieval stale)** → **#3 (searxng)**
- Mauro recomienda arreglarlos "cuando tenga sentido", no todo de una — priorizar los que más afectan la experiencia de uso
