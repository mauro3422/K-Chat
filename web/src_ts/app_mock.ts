/**
 * K-Chat TS Prototype â€” Orchestrator
 *
 * All pieces wired together via dependency injection (Lego blocks).
 * Uses StreamSimulator to generate realistic NDJSON events dynamically.
 * SessionStore replaces mock session data.
 * SSEClient is instantiated and ready for real backend connection.
 */

import { TypedEventBus } from './core/infra/EventBus';
import { ChatForm } from './core/ui/ChatForm';
import { FileUploader } from './core/ui/FileUploader';
import { MessageView } from './rendering/MessageView';
import { SessionList } from './core/session/SessionList';
import { WidgetRegistry } from './core/widget/WidgetRegistry';
import { IframeBuilder } from './rendering/IframeBuilder';
import { WidgetContainerRenderer } from './rendering/WidgetContainerRenderer';
import { StreamSimulator } from './streaming/StreamSimulator';
import { StreamOrchestrator } from './streaming/StreamOrchestrator';
import { RetryController } from './core/ui/RetryHandler';
import { DebugManager } from './core/debug/DebugManager';
import { SessionStore } from './core/session/SessionStore';
import { NDJSONStreamClient } from './streaming/NDJSONStreamClient';
import { SSEClient } from './streaming/SSEClient';
import { ApiClient } from './api/ApiClient';
import { WidgetStateManager } from './core/widget/WidgetStateManager';
import { CanvasWorkspace } from './widgets/CanvasWorkspace';
import { CanvasCardManager } from './widgets/CanvasCardManager';
import { CanvasLayoutStore } from './widgets/CanvasLayoutStore';
import { SkillsUI } from './widgets/SkillsUI';
import { ModelSelector } from './widgets/ModelSelector';
import { NotificationService } from './core/notification/NotificationService';
import { RateLimitCooldown } from './core/notification/RateLimitCooldown';
import { ToastUI } from './core/notification/ToastUI';
import { NotificationBell } from './core/notification/NotificationBell';
import { CSSInjector } from './core/infra/CSSInjector';
import { AudioBus } from './core/notification/AudioBus';
import { GridController } from './core/ui/GridController';
import { CanvasOverlay } from './widgets/CanvasOverlay';
import { LanStatusPanel } from './widgets/LanStatusPanel';
import { MemoryStatusPanel } from './widgets/MemoryStatusPanel';
import { HealthOverviewPanel } from './widgets/HealthOverviewPanel';
import { getLogger } from './core/infra/LoggerFactory';
import { SystemLogPanel } from './core/debug/SystemLogPanel';
import { BrowserDomRenderer } from './rendering/DomRenderer';

document.addEventListener('DOMContentLoaded', async () => {
  const markedGlobal = (window as Window & { marked?: { parse?: (text: string, opts?: Record<string, unknown>) => string } | ((text: string) => string) }).marked;
  if (!markedGlobal) {
    throw new Error('marked.js is required before booting the UI');
  }
  const domPurifyGlobal = (window as Window & { DOMPurify?: { sanitize: (html: string, config?: Record<string, unknown>) => string } }).DOMPurify;
  if (!domPurifyGlobal) {
    throw new Error('DOMPurify is required before booting the UI');
  }
  const markedFn = (text: string): string => {
    if (typeof markedGlobal === 'function') {
      return markedGlobal(text);
    }
    return markedGlobal.parse ? markedGlobal.parse(text, { breaks: true, gfm: true }) : text;
  };
  const dompurifyFn = domPurifyGlobal;
  // â”€â”€ 1. Init Lego Blocks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
  const domRenderer = new BrowserDomRenderer(markedFn, dompurifyFn, widgetRegistry);
  const renderMarkdownFn = domRenderer.renderMarkdown.bind(domRenderer);
  const messageView = new MessageView(domRenderer, iframeBuilder, containerRenderer);
  const chatForm = new ChatForm(eventBus, fileUploader);
  const sessionList = new SessionList(eventBus);
  const streamSimulator = new StreamSimulator();
  const sessionStore = new SessionStore(apiClient);
  const ndjsonClient = new NDJSONStreamClient(apiClient, eventBus);

  const sseClient = new SSEClient(eventBus, messageView, iframeBuilder, containerRenderer, widgetRegistry, renderMarkdownFn, debug);
  sseClient.connect();
  sseClient.setCurrentSessionId(sessionStore.activeSessionId);

  const notificationService = new NotificationService(eventBus);
  const rateLimitCooldown = new RateLimitCooldown(eventBus);
  const toastUI = new ToastUI(eventBus);
  toastUI.init();

  const notificationBell = new NotificationBell(eventBus);
  notificationBell.init();

  // Wire rate-limit:detected (from SSEClient) â†’ RateLimitCooldown
  eventBus.on<{ duration: number }>('rate-limit:detected', (data) => {
    rateLimitCooldown.start(data.duration);
    notificationService.show('warning', 'â³ LÃ­mite de tasa alcanzado. EsperÃ¡ al countdown.', 8000);
  });

  const skillsUI = new SkillsUI(eventBus, renderMarkdownFn, window.fetch.bind(window));
  const modelSelector = new ModelSelector();
  const systemLogPanel = new SystemLogPanel(apiClient);
  const lanStatusPanel = new LanStatusPanel(apiClient, getLogger('lan-status'));
  const memoryStatusPanel = new MemoryStatusPanel(apiClient, getLogger('memory-status'));
  const healthOverviewPanel = new HealthOverviewPanel(apiClient, getLogger('health-overview'));
  skillsUI.init();
  modelSelector.init();
  systemLogPanel.init();
  lanStatusPanel.init();
  memoryStatusPanel.init();
  healthOverviewPanel.init();

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
  const appEl = document.getElementById('app');
  const initialSessionId = appEl?.dataset.sessionId;
  await sessionStore.init(eventBus, initialSessionId);
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

  // â”€â”€ 2. Stream Orchestrator â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const retryController = new RetryController(debug);
  const streamOrchestrator = new StreamOrchestrator(
    messageView, streamSimulator, sessionStore, chatForm,
    iframeBuilder, containerRenderer, widgetRegistry, renderMarkdownFn,
    rateLimitCooldown, debug, retryController,
    ndjsonClient, // IA real conectada
    eventBus,
  );

  // â”€â”€ 3. UI Refresh â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const refreshUI = () => {
    sessionList.renderSessions(sessionStore.sessions, sessionStore.activeSessionId);
    messageView.clearContainer();
    sessionStore.activeHistory.forEach((msg) => messageView.appendMessage(msg));
    // Scroll to the last assistant message after loading a session
    const msgsEl = document.getElementById('messages');
    if (msgsEl) {
      const lastAssistant = msgsEl.querySelector('.msg.assistant:last-child') as HTMLElement | null;
      if (lastAssistant) {
        msgsEl.scrollTop = lastAssistant.offsetTop;
      } else {
        msgsEl.scrollTop = msgsEl.scrollHeight;
      }
    }
  };
  refreshUI();

  // â”€â”€ 4. SessionStore Events â†’ UI â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  // SessionStore handles data mutations; we only update UI + debug logs.

  eventBus.on('sessions:updated', () => {
    sessionList.renderSessions(sessionStore.sessions, sessionStore.activeSessionId);
  });

  eventBus.on('history:updated', () => {
    // Stream adds messages to DOM directly. This handler only needed for
    // session switching (handled by session:selected â†’ refreshUI).
    // Full re-render here would destroy scroll position.
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
    debug.logUI('rename_session', `${data.id} â†’ ${data.name}`);
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
    refreshUI();
    // Ensure empty state for new session
    const msgsEl = document.getElementById('messages');
    if (msgsEl && msgsEl.children.length === 0) {
      msgsEl.innerHTML = '<div class="empty-state">EnvÃ­a un mensaje para empezar</div>';
    }
  });

  // â”€â”€ 5. New Session button â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  let _creatingSession = false;
  document.getElementById('btn-new-session')?.addEventListener('click', async () => {
    if (_creatingSession) return;
    _creatingSession = true;
    const id = await sessionStore.createSession();
    _creatingSession = false;
    if (id) logger.info('session_created', id);
  });

  // â”€â”€ 6. Event Bus Bindings â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
          debug.logUI('retry', `intento ${retryCount + 1} â€” "${userText.substring(0, 40)}"`);
          streamOrchestrator.handleRetry(userText);
        }
      }
    });
  }

  // Stream: abort (user clicked stop or pressed Escape)
  eventBus.on('stream:abort', () => {
    streamOrchestrator.abort();
  });

  // â”€â”€ 7. SSE Event Handling â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  eventBus.on<{ id: string }>('sse:session-deleted', (data) => {
    // Guard: only delete if session still exists (breaks SSE echo loop)
    if (sessionStore.sessions.some(s => s.id === data.id)) {
      sessionStore.deleteSession(data.id);
    }
  });

  eventBus.on<{ sessionId: string; messageId: number }>('sse:message-deleted', () => {
    // Handled by SSEClient's DOM removal; store update via session mutation if needed
  });

  eventBus.on<{ sessionId: string; message: import('./types/messages').MessageData; isCurrentSession: boolean }>('sse:new-message', (data) => {
    if (data.isCurrentSession) {
      sessionStore.addMessage(data.sessionId, data.message);
    } else {
      sessionList.markUnread(data.sessionId);
    }
  });

  eventBus.on<{ sessionId: string }>('session:select', (data) => {
    sessionList.clearUnread(data.sessionId);
    void sessionStore.selectSession(data.sessionId);
  });

  // â”€â”€ 8. Browser History Navigation (back/forward) â”€â”€â”€â”€â”€
  window.addEventListener('popstate', (event) => {
    const state = event.state as { sessionId?: string } | null;
    if (state?.sessionId && sessionStore.sessions.some(s => s.id === state.sessionId)) {
      void sessionStore.selectSession(state.sessionId);
    }
  });

  // â”€â”€ 9. Sidebar Toggle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const sidebarToggle = document.getElementById('sidebar-toggle');
  const sidebarEl = document.getElementById('sidebar');
  const gutterEl = document.getElementById('sidebar-gutter');

  if (sidebarToggle && sidebarEl) {
    sidebarToggle.addEventListener('click', () => {
      sidebarEl.classList.toggle('collapsed');
      sidebarToggle.textContent = sidebarEl.classList.contains('collapsed') ? '▶' : '◀';
      sidebarToggle.title = sidebarEl.classList.contains('collapsed') ? 'Mostrar panel' : 'Ocultar panel';
      if (debugPanel && debugPanel.classList.contains('open')) debug.refresh();
    });
  }

  // Gutter drag
  let isDragging = false;
  const MIN_SIDEBAR_WIDTH = 160;
  const MAX_SIDEBAR_WIDTH = 500;

  function onGutterDown(e: MouseEvent) {
    if (sidebarEl?.classList.contains('collapsed')) return;
    isDragging = true;
    gutterEl?.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  }

  function onGutterMove(e: MouseEvent) {
    if (!isDragging || !sidebarEl) return;
    const newWidth = Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, e.clientX));
    sidebarEl.style.width = newWidth + 'px';
    localStorage.setItem('sidebar_width', String(newWidth));
  }

  function onGutterUp() {
    if (!isDragging) return;
    isDragging = false;
    gutterEl?.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }

  if (gutterEl) {
    gutterEl.addEventListener('mousedown', onGutterDown);
    gutterEl.addEventListener('touchstart', (e: TouchEvent) => {
      if (!sidebarEl || sidebarEl.classList.contains('collapsed')) return;
      isDragging = true;
      gutterEl.classList.add('dragging');
      document.body.style.userSelect = 'none';
      const touch = e.touches[0];
      const newWidth = Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, touch.clientX));
      sidebarEl.style.width = newWidth + 'px';
      localStorage.setItem('sidebar_width', String(newWidth));
      e.preventDefault();
    }, { passive: false });
  }
  document.addEventListener('mousemove', onGutterMove);
  document.addEventListener('mouseup', onGutterUp);
  document.addEventListener('touchmove', (e) => {
    if (!isDragging || !sidebarEl) return;
    const touch = e.touches[0];
    const newWidth = Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, touch.clientX));
    sidebarEl.style.width = newWidth + 'px';
    localStorage.setItem('sidebar_width', String(newWidth));
  }, { passive: true });
  document.addEventListener('touchend', onGutterUp);

  document.getElementById('theme-toggle')?.addEventListener('click', () => {
    const isLight = document.body.classList.toggle('light-theme');
    document.documentElement.classList.toggle('light-theme', isLight);
    localStorage.setItem('selected_theme', isLight ? 'light' : 'dark');
  });

  // â”€â”€ 11. Debug Panel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

  // Periodic refresh â€” store ID for cleanup
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
      // Auto-load session debug info (reasoning, context, system prompt, etc.)
      const sid = sessionStore.activeSessionId;
      if (sid) {
        debug.loadDebugInfo(sid);
      }
      debug.refresh();
      systemLogPanel.refresh();
    }
  }, 400);

  const lanStatusIntervalId = setInterval(() => {
    void lanStatusPanel.refresh();
  }, 5000);
  void lanStatusPanel.refresh();

  const memoryStatusIntervalId = setInterval(() => {
    void memoryStatusPanel.refresh();
  }, 7000);
  void memoryStatusPanel.refresh();

  const healthOverviewIntervalId = setInterval(() => {
    void healthOverviewPanel.refresh();
  }, 9000);
  void healthOverviewPanel.refresh();
  window.addEventListener('beforeunload', () => {
    clearInterval(debugIntervalId);
    clearInterval(lanStatusIntervalId);
    clearInterval(memoryStatusIntervalId);
    clearInterval(healthOverviewIntervalId);
    streamOrchestrator.abort();
    ndjsonClient.abort();
    sseClient.disconnect();
    notificationBell?.dispose();
    sessionStore?.dispose();
    canvasWorkspace?.dispose();
    widgetRegistry.reset();
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

  logger.info('TS ready â€” Lego layout blocks initialized');
  logger.info('Try: __k.canvasOverlay.startEffect("rain")');
});
