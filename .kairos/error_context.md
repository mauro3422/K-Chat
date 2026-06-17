# ⚡ CRASH RECOVERY — SERVER_DOWN
Detected: 2026-06-16 22:50:39

---

## What Happened
Server became unresponsive after 90s of uptime.
Consecutive health check failures: 4
This likely means a recent code edit caused a runtime error.


## Last Commits
c7d4218 fix: sistema de auto-inyeccion de memorias no funcionaba
8046c2e feat: ambos frontends funcionando simultaneamente + composition root completo
2515502 refactor(backend): Fase 4 — routers usan app.state con fallback a singletons
c65a244 tests para 16 tools core + diseno FASE 5 Proactividad
bcecc0d refactor(backend): Fase 1-3 migracion Lego — composition root + DI


## Uncommitted Changes (likely culprit)
```diff
diff --git a/src/memory/migrations.py b/src/memory/migrations.py
index ab1ed24..a21f7d1 100644
--- a/src/memory/migrations.py
+++ b/src/memory/migrations.py
@@ -212,11 +212,17 @@ async def _migration_010_memory_index(conn, engine):
 
 
 async def _migration_011_cleanup_orphans(conn, engine):
-    # Clean orphaned records from sessions that were deleted
-    for table in ('widget_states', 'memory_index', 'messages', 'tool_calls', 'debug_info'):
-        await engine.execute(conn, f"""
-            DELETE FROM {table} WHERE session_id NOT IN (SELECT session_id FROM sessions)
-        """)
+    # Clean orphaned records from sessions that were deleted.
+    # Skip tables that have been migrated to global schema (no session_id column).
+    for table in ('widget_states', 'messages', 'tool_calls', 'debug_info', 'memory_index'):
+        try:
+            await engine.execute(conn, f"""
+                DELETE FROM {table} WHERE session_id NOT IN (SELECT session_id FROM sessions)
+            """)
+        except Exception:
+            # Table may have been converted to global schema (memory_index)
+            # or column doesn't exist — skip gracefully.
+            pass
     # Add cleanup triggers: when a session is deleted, cascade cleanups
     triggers = [
         ('trg_cleanup_widget_states', 'widget_states'),
diff --git a/web/routers/sessions.py b/web/routers/sessions.py
index 79b7a8c..edb0cd4 100644
--- a/web/routers/sessions.py
+++ b/web/routers/sessions.py
@@ -4,7 +4,6 @@ from fastapi import APIRouter, Body, Request
 from fastapi.responses import JSONResponse
 
 from src.api.repos import get_repos
-from src.memory.repos.protocols import MessageRecord
 
 logger = logging.getLogger(__name__)
 
@@ -19,6 +18,15 @@ async def rename(session_id: str, request: Request, name: str = Body(..., embed=
     return JSONResponse({"status": "ok"})
 
 
+@router.post("/sessions/create")
+async def create_session(request: Request) -> JSONResponse:
+    """Create a new session and return its id."""
+    repos = getattr(request.app.state, 'repos', None) or get_repos()
+    from src.api.session import ensure_session
+    sid = await ensure_session(session_repo=repos.sessions)
+    return JSONResponse({"id": sid})
+
+
 @router.get("/sessions")
 async def list_sessions(request: Request) -> JSONResponse:
     """JSON endpoint for sessions list (used by TS prototype)."""
diff --git a/web/src_ts/api/ApiClient.ts b/web/src_ts/api/ApiClient.ts
index 3335623..8a15b99 100644
--- a/web/src_ts/api/ApiClient.ts
+++ b/web/src_ts/api/ApiClient.ts
@@ -30,6 +30,18 @@ export class ApiClient implements IChatApi, ISessionApi, IWidgetApi, IDebugApi {
     });
   }
 
+  getSessions(): Promise<Response> {
+    return fetch(`${this.baseUrl}/sessions`);
+  }
+
+  createSession(): Promise<Response> {
+    return fetch(`${this.baseUrl}/sessions/create`, { method: 'POST' });
+  }
+
+  getSessionMessages(sessionId: string): Promise<Response> {
+    return fetch(`${this.baseUrl}/sessions/${sessionId}/messages`);
+  }
+
   sidebar(currentSessionId?: string): Promise<Response> {
     let url = `${this.baseUrl}/sidebar`;
     if (currentSessionId) {
diff --git a/web/src_ts/app_mock.ts b/web/src_ts/app_mock.ts
index 071598c..59b840e 100644
--- a/web/src_ts/app_mock.ts
+++ b/web/src_ts/app_mock.ts
@@ -38,7 +38,7 @@ import { GridController } from './core/ui/GridController';
 import { CanvasOverlay } from './widgets/CanvasOverlay';
 import { getLogger } from './core/LoggerFactory';
 
-document.addEventListener('DOMContentLoaded', () => {
+document.addEventListener('DOMContentLoaded', async () => {
 
   // ── 1. Init Lego Blocks ──────────────────────────────
   const eventBus = new TypedEventBus();
@@ -60,7 +60,7 @@ document.addEventListener('DOMContentLoaded', () => {
   const chatForm = new ChatForm(eventBus, fileUploader);
   const sessionList = new SessionList(eventBus);
   const streamSimulator = new StreamSimulator();
-  const sessionStore = new SessionStore();
+  const sessionStore = new SessionStore(apiClient);
   const ndjsonClient = new NDJSONStreamClient(apiClient, eventBus);
 
   const sseClient = new SSEClient(eventBus, messageView, iframeBuilder, containerRenderer, widgetRegistry, debug);
@@ -89,7 +89,7 @@ document.addEventListener('DOMContentLoaded', () => {
   messageView.init();
   chatForm.init();
   sessionList.init();
-  sessionStore.init(eventBus);
+  await sessionStore.init(eventBus);
   gridController.init();
   canvasOverlay.init();
   audioBus.init();
diff --git a/web/src_ts/core/session/SessionStore.ts b/web/src_ts/core/session/SessionStore.ts
index 1d8a242..548d758 100644
--- a/web/src_ts/core/session/SessionStore.ts
+++ b/web/src_ts/core/session/SessionStore.ts
@@ -1,76 +1,43 @@
 import { IEventBus, EventCallback } from '../../types/events';
 import { MessageData } from '../../rendering/MessageView';
-import { randomWidget } from '../../widgets/templates';
+import { ApiClient } from '../../api/ApiClient';
+import { getLogger } ...
```

## Staged Changes
```

```

---

*This file was written by the watchdog on crash detection.
It will be read by the system prompt builder on next startup.
Kairos will see this and can auto-fix the issue.*
