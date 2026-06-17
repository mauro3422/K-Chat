/**
 * K-Chat TS Prototype — Orchestrator
 *
 * All pieces wired together via dependency injection (Lego blocks).
 * Uses StreamSimulator to generate realistic NDJSON events dynamically.
 * SessionStore replaces mock session data.
 * SSEClient is instantiated and ready for real backend connection.
 */

import { TypedEventBus } from './core/EventBus';
import { ChatForm } from './core/ChatForm';
import { FileUploader } from './core/FileUploader';
import { MessageView } from './rendering/MessageView';
import { SessionList } from './core/SessionList';
import { WidgetRegistry } from './core/WidgetRegistry';
import { IframeBuilder } from './rendering/IframeBuilder';
import { WidgetContainerRenderer } from './rendering/WidgetContainerRenderer';
import { StreamSimulator } from './streaming/StreamSimulator';
import { StreamOrchestrator } from './streaming/StreamOrchestrator';
import { RetryController } from './core/ui/RetryHandler';
import { DebugManager } from './core/DebugManager';
import { SessionStore } from './core/SessionStore';
import { NDJSONStreamClient } from './streaming/NDJSONStreamClient';
import { SSEClient } from './streaming/SSEClient';
import { ApiClient } from './api/ApiClient';
import { WidgetStateManager } from './core/WidgetStateManager';
import { CanvasWorkspace } from './widgets/CanvasWorkspace';
import { CanvasCardManager } from './widgets/CanvasCardManager';
import { CanvasLayoutStore } from './widgets/CanvasLayoutStore';
import { SkillsUI } from './widgets/SkillsUI';
import { NotificationService } from './core/NotificationService';
import { RateLimitCooldown } from './core/RateLimitCooldown';
import { ToastUI } from './core/ToastUI';
import { NotificationBell } from './core/NotificationBell';
import { CSSInjector } from './core/infra/CSSInjector';
import { AudioBus } from './core/notification/AudioBus';
import { GridController } from './core/ui/GridController';
import { CanvasOverlay } from './widgets/CanvasOverlay';
import { getLogger } from './core/LoggerFactory';
import { SystemLogPanel } from './core/debug/SystemLogPanel';

document.addEventListener('DOMContentLoaded', async () => {

  // ── 1. Init Lego Blocks ──────────────────────────────
  const eventBus = new TypedEventBus();
  const debug = new DebugManager();
  const widgetRegistry = new WidgetRegistry();
  const apiClient = new ApiClient();
  const widgetStateManager = new WidgetStateManager(apiClient);
  const iframeBuilder = new IframeBuilder(widgetRegistry, debug, widgetStateManager);
  const containerRenderer = new WidgetContainerRenderer(iframeBuilder, debug);
  const cssInjector = new CSSInjector();
  const audioBus = new AudioBus(eventBus);
  const gridController = new GridController();
  const canvasOverlay = new CanvasOverlay();
  const layoutStore = new CanvasLayoutStore();
  const cardManager = new CanvasCardManager(iframeBuilder, widgetRegistry, eventBus, debug);

  const fileUploader = new FileUploader();
  const messageView = new MessageView(undefined, iframeBuilder, containerRenderer);
  const chatForm = new ChatForm(eventBus, fileUploader);
  const sessionList = new SessionList(eventBus);
  const streamSimulator = new StreamSimulator();
  const sessionStore = new SessionStore(apiClient);
  const ndjsonClient = new NDJSONStreamClient(apiClient, eventBus);

  const sseClient = new SSEClient(eventBus, messageView, iframeBuilder, containerRenderer, widgetRegistry, debug);
  sseClient.connect();
  sseClient.setCurrentSessionId(sessionStore.activeSessionId);

  const notificationService = new NotificationService(eventBus);
  const rateLimitCooldown = new RateLimitCooldown(eventBus);
  const toastUI = new ToastUI(eventBus);
  toastUI.init();

  const notificationBell = new NotificationBell(eventBus);
  notificationBell.init();

  // Wire rate-limit:detected (from SSEClient) → RateLimitCooldown
  eventBus.on<{ duration: number }>('rate-limit:detected', (data) => {
    rateLimitCooldown.start(data.duration);
    notificationService.show('warning', '⏳ Límite de tasa alcanzado. Esperá al countdown.', 8000);
  });

  const skillsUI = new SkillsUI(eventBus);
  const systemLogPanel = new SystemLogPanel(apiClient);
  skillsUI.init();
  systemLogPanel.init();

  window.addEventListener('kairos:ui-log', (event) => {
    const detail = (event as CustomEvent<{ label?: string; detail?: string }>).detail;
    if (!detail?.label) return;
    debug.logUI(detail.label, detail.detail || '');
  });

  debug.init();
  fileUploader.init();
  messageView.init();
  chatForm.init();
  sessionList.init();
  await sessionStore.init(eventBus);
  gridController.init();
  canvasOverlay.init();
  audioBus.init();
  const canvasWorkspace = new CanvasWorkspace(iframeBuilder, widgetRegistry, eventBus, cardManager, layoutStore);
  canvasWorkspace.init(sessionStore.activeSessionId);

  const logger = getLogger('app', eventBus, apiClient, debug);
  logger.info('Sistema inicializado');

  // Handle postMessage from widget iframes
  window.addEventListener('message', (event) => {
    iframeBuilder.handleMessage(event);
  });

  // ── 2. Stream Orchestrator ────────────────────────────
  const retryController = new RetryController(debug);
  const streamOrchestrator = new StreamOrchestrator(
    messageView, streamSimulator, sessionStore, chatForm,
    iframeBuilder, containerRenderer, widgetRegistry,
    rateLimitCooldown, debug, retryController,
    ndjsonClient, // IA real conectada
    eventBus,
  );

  // ── 3. UI Refresh ────────────────────────────────────
  const refreshUI = () => {
    sessionList.renderSessions(sessionStore.sessions, sessionStore.activeSessionId);
    messageView.clearContainer();
    sessionStore.activeHistory.forEach((msg) => messageView.appendMessage(msg));
  };
  refreshUI();

  // ── 4. SessionStore Events → UI ──────────────────────
  // SessionStore handles data mutations; we only update UI + debug logs.

  eventBus.on('sessions:updated', () => {
    sessionList.renderSessions(sessionStore.sessions, sessionStore.activeSessionId);
  });

  eventBus.on('history:updated', () => {
    // Full refresh only when not streaming (stream updates DOM directly)
    if (!streamOrchestrator.isStreaming) {
      messageView.clearContainer();
      sessionStore.activeHistory.forEach((msg) => messageView.appendMessage(msg));
    }
  });

  eventBus.on<{ id: string }>('session:selected', (data) => {
    debug.logUI('select_session', data.id);
    sseClient.setCurrentSessionId(data.id);
    sseClient.setLoadingSession(true);
    canvasWorkspace.reset();
    canvasWorkspace.init(data.id);
    refreshUI();
    sseClient.setLoadingSession(false);
  });

  eventBus.on<{ id: string; name: string }>('session:renamed', (data) => {
    debug.logUI('rename_session', `${data.id} → ${data.name}`);
  });

  eventBus.on<{ id: string }>('session:deleted', (data) => {
    debug.logUI('delete_session', data.id);
    widgetRegistry.reset();
    iframeBuilder.reset();
    canvasWorkspace.reset();
    canvasWorkspace.init(sessionStore.activeSessionId);
    // Force UI refresh: clear messages and reload new active session
    messageView.clearContainer();
    sessionStore.activeHistory.forEach((msg) => messageView.appendMessage(msg));
  });

  eventBus.on<{ id: string }>('session:created', (data) => {
    debug.logUI('new_session', data.id);
    widgetRegistry.reset();
    iframeBuilder.reset();
    canvasWorkspace.reset();
    canvasWorkspace.init(data.id);
  });

  // ── 5. New Session button ────────────────────────────
  document.getElementById('btn-new-session')?.addEventListener('click', async () => {
    const id = await sessionStore.createSession();
    if (id) logger.info('session_created', id);
  });

  // ── 6. Event Bus Bindings ────────────────────────────

  // Chat: send message
  eventBus.on<{ text: string; files?: File[]; model?: string }>('chat:send', (data) => {
    streamOrchestrator.handleChatSend(data.text, data.files, data.model);
  });

  // Retry: error card retry button clicks (event delegation on #messages)
  const messagesEl = document.getElementById('messages');
  if (messagesEl) {
    messagesEl.addEventListener('click', (e: Event) => {
      const btn = (e.target as HTMLElement).closest('.error-retry-btn') as HTMLElement | null;
      if (btn) {
        const msgEl = btn.closest('.msg.assistant') as HTMLElement | null;
        const userText = msgEl?.dataset.userText;
        if (userText) {
          const retryCount = parseInt(msgEl?.dataset.retryCount || '0', 10);
          msgEl!.dataset.retryCount = String(retryCount + 1);
          debug.logUI('retry', `intento ${retryCount + 1} — "${userText.substring(0, 40)}"`);
          streamOrchestrator.handleRetry(userText);
        }
      }
    });
  }

  // Stream: abort (user clicked stop or pressed Escape)
  eventBus.on('stream:abort', () => {
    streamOrchestrator.abort();
  });

  // ── 7. SSE Event Handling ─────────────────────────────
  eventBus.on<{ id: string }>('sse:session-deleted', (data) => {
    sessionStore.deleteSession(data.id);
  });

  eventBus.on<{ sessionId: string; messageId: number }>('sse:message-deleted', () => {
    // Handled by SSEClient's DOM removal; store update via session mutation if needed
  });

  eventBus.on<{ sessionId: string; message: import('./rendering/MessageView').MessageData; isCurrentSession: boolean }>('sse:new-message', (data) => {
    if (data.isCurrentSession) {
      sessionStore.addMessage(data.sessionId, data.message);
    } else {
      sessionList.markUnread(data.sessionId);
    }
  });

  eventBus.on<{ sessionId: string }>('session:select', (data) => {
    sessionList.clearUnread(data.sessionId);
  });

  // ── 8. Sidebar Toggle ────────────────────────────────
  const sidebarToggle = document.getElementById('sidebar-toggle');
  const sidebarEl = document.getElementById('sidebar');

  if (sidebarToggle && sidebarEl) {
    sidebarToggle.addEventListener('click', () => {
      sidebarEl.classList.toggle('collapsed');
      sidebarToggle.textContent = sidebarEl.classList.contains('collapsed') ? '▶' : '◀';
      sidebarToggle.title = sidebarEl.classList.contains('collapsed') ? 'Mostrar panel' : 'Ocultar panel';
      if (debugPanel && debugPanel.classList.contains('open')) debug.refresh();
    });
  }

  // ── 9. Theme Toggle ──────────────────────────────────
  document.getElementById('theme-toggle')?.addEventListener('click', () => {
    const isLight = document.body.classList.toggle('light-theme');
    document.documentElement.classList.toggle('light-theme', isLight);
    localStorage.setItem('selected_theme', isLight ? 'light' : 'dark');
  });

  // ── 10. Debug Panel ──────────────────────────────────
  const debugToggle = document.getElementById('debug-toggle');
  const debugPanel = document.getElementById('debug-panel');
  const debugClose = document.getElementById('debug-close');
  const mainEl = document.getElementById('main');

  function toggleDebug() {
    if (!debugPanel) return;
    const isOpen = debugPanel.classList.contains('open');
    debugPanel.classList.toggle('open');
    if (mainEl) mainEl.classList.toggle('shifted');
    if (!isOpen) { debug.setActiveMessage(null, null); debug.refresh(); }
  }

  if (debugToggle) {
    debugToggle.addEventListener('click', (e) => {
      e.preventDefault();
      toggleDebug();
    });
  }

  if (debugClose && debugPanel) {
    debugClose.addEventListener('click', (e) => {
      e.preventDefault();
      toggleDebug();
    });
  }

  // Periodic refresh — store ID for cleanup
  const debugIntervalId = setInterval(() => {
    if (debugPanel && debugPanel.classList.contains('open')) {
      const activeCtx = streamOrchestrator.debugActiveContext;
      if (activeCtx) {
        const streamingMsg = document.querySelector('#messages .msg.assistant.live-msg') as HTMLElement | null;
        const msgEl = streamingMsg || streamOrchestrator.debugLastAssistantMsgEl;
        debug.setActiveMessage(msgEl, {
          phaseIndex: activeCtx.phaseIndex,
          firstToken: activeCtx.firstToken,
          reasoningTexts: activeCtx.reasoningTexts,
          contentTexts: activeCtx.contentTexts,
        });
      } else {
        const lastMsg = streamOrchestrator.debugLastAssistantMsgEl || document.querySelector('#messages .msg.assistant:last-child') as HTMLElement | null;
        debug.setActiveMessage(lastMsg, null);
      }
      debug.refresh();
      systemLogPanel.refresh();
    }
  }, 400);
  window.addEventListener('beforeunload', () => {
    clearInterval(debugIntervalId);
    notificationBell?.dispose();
    sessionStore?.dispose();
    canvasWorkspace?.dispose();
    eventBus.removeAllListeners();
  });

  // Expose Lego blocks for AI / widget access
  (window as any).__k = {
    cssInjector,
    audioBus,
    gridController,
    canvasOverlay,
    eventBus,
  };

  logger.info('TS ready — Lego layout blocks initialized');
  logger.info('Try: __k.canvasOverlay.startEffect("rain")');
});
