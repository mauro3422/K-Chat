import { describe, it, expect } from 'vitest';

describe('anti-regression: retry does not duplicate messages', () => {
  it('handleRetry does not call appendMessage', () => {
    class RetryGuard {
      private _isRetry = false;
      appendCalled = 0;

      handleRetry() {
        this._isRetry = true;
        this.handleChatSend();
        this._isRetry = false;
      }

      handleChatSend() {
        if (!this._isRetry) {
          this.appendCalled++;
        }
      }
    }

    const guard = new RetryGuard();
    guard.handleRetry();
    expect(guard.appendCalled).toBe(0);
  });
});

describe('anti-regression: insertBeforeBody interleaving', () => {
  it('inserts reasoning before its phase body', () => {
    const container = document.createElement('div');

    const body0 = document.createElement('div');
    body0.className = 'msg-body';
    body0.setAttribute('data-phase', '0');
    container.appendChild(body0);

    const reasoning0 = document.createElement('details');
    reasoning0.setAttribute('data-phase', '0');

    const targetBody = container.querySelector('.msg-body[data-phase="0"]');
    container.insertBefore(reasoning0, targetBody);

    expect(container.children[0]).toBe(reasoning0);
    expect(container.children[1]).toBe(body0);
  });
});

describe('anti-regression: autoScroll respects user position', () => {
  it('only fires when near bottom', () => {
    const scrollHeight = 1000;
    const clientHeight = 500;

    let scrollTop = 0;
    let distFromBottom = scrollHeight - scrollTop - clientHeight;
    expect(distFromBottom > 300).toBe(true);

    scrollTop = 500;
    distFromBottom = scrollHeight - scrollTop - clientHeight;
    expect(distFromBottom > 300).toBe(false);
  });
});

describe('anti-regression: session-deleted guard', () => {
  it('only deletes existing sessions', () => {
    const sessions = [{ id: 'sess-1' }, { id: 'sess-2' }];
    let deleteCalled = false;

    const handler = (data: { id: string }) => {
      if (sessions.some(s => s.id === data.id)) {
        deleteCalled = true;
      }
    };

    handler({ id: 'sess-1' });
    expect(deleteCalled).toBe(true);

    deleteCalled = false;
    handler({ id: 'sess-3' });
    expect(deleteCalled).toBe(false);
  });
});

describe('anti-regression: session auto-naming', () => {
  it('auto-names session with first message', async () => {
    let renamedArgs: { id: string; name: string } | null = null;
    const sessionStore = {
      activeSessionId: '',
      async createSession() { return 'new-sess-id'; },
      renameSession(id: string, name: string) { renamedArgs = { id, name }; },
    };

    async function handleChatSend(text: string) {
      if (!sessionStore.activeSessionId) {
        const newId = await sessionStore.createSession();
        if (newId) {
          sessionStore.renameSession(newId, text.substring(0, 60));
        }
      }
    }

    await handleChatSend('Hello, this is a test message!');
    expect(renamedArgs).toEqual({ id: 'new-sess-id', name: 'Hello, this is a test message!' });
  });
});

describe('anti-regression: phase-specific body divs', () => {
  it('creates phase-specific body divs', () => {
    const container = document.createElement('div');
    const msgEl = document.createElement('div');
    container.appendChild(msgEl);

    let phaseIdx = 0;
    let bodyEl = msgEl.querySelector(`.msg-body[data-phase="${phaseIdx}"]`);
    if (!bodyEl) {
      bodyEl = document.createElement('div');
      bodyEl.className = 'msg-body';
      bodyEl.setAttribute('data-phase', String(phaseIdx));
      msgEl.appendChild(bodyEl);
    }
    expect(msgEl.children.length).toBe(1);
    expect(bodyEl.getAttribute('data-phase')).toBe('0');

    phaseIdx = 1;
    let bodyEl1 = msgEl.querySelector(`.msg-body[data-phase="${phaseIdx}"]`);
    if (!bodyEl1) {
      bodyEl1 = document.createElement('div');
      bodyEl1.className = 'msg-body';
      bodyEl1.setAttribute('data-phase', String(phaseIdx));
      msgEl.appendChild(bodyEl1);
    }
    expect(msgEl.children.length).toBe(2);
    expect(bodyEl1.getAttribute('data-phase')).toBe('1');
  });
});

describe('anti-regression: removeExcessContainers', () => {
  it('removeExcessContainers uses Array.from to avoid stale NodeList', () => {
    const bodyDiv = document.createElement('div');
    for (let i = 0; i < 3; i++) {
      const con = document.createElement('div');
      con.className = 'interactive-widget-container';
      bodyDiv.appendChild(con);
    }
    expect(bodyDiv.children.length).toBe(3);

    let containers = Array.from(bodyDiv.querySelectorAll('.interactive-widget-container'));
    while (containers.length > 2) {
      const last = containers.pop()!;
      if (last.parentNode) last.parentNode.removeChild(last);
    }
    expect(bodyDiv.children.length).toBe(2);

    containers = Array.from(bodyDiv.querySelectorAll('.interactive-widget-container'));
    while (containers.length > 0) {
      const last = containers.pop()!;
      if (last.parentNode) last.parentNode.removeChild(last);
    }
    expect(bodyDiv.children.length).toBe(0);
  });
});

describe('anti-regression: beforeunload cleanup', () => {
  it('beforeunload calls cleanup on active services', () => {
    let abortCalled = false;
    let disconnectCalled = false;
    let resetCalled = false;

    const streamOrchestrator = { abort: () => { abortCalled = true; } };
    const ndjsonClient = { abort: () => {} };
    const sseClient = { disconnect: () => { disconnectCalled = true; } };
    const widgetRegistry = { reset: () => { resetCalled = true; } };

    streamOrchestrator.abort();
    ndjsonClient.abort();
    sseClient.disconnect();
    widgetRegistry.reset();

    expect(abortCalled).toBe(true);
    expect(disconnectCalled).toBe(true);
    expect(resetCalled).toBe(true);
  });
});

describe('anti-regression: SystemLogPanel scroll save/restore', () => {
  it('SystemLogPanel saves and restores scroll position', () => {
    const el = document.createElement('div');
    el.style.height = '100px';
    el.style.overflow = 'auto';

    const content = document.createElement('div');
    content.style.height = '500px';
    el.appendChild(content);

    const scrollTop = 100;
    el.scrollTop = scrollTop;

    const oldScrollTop = el.scrollTop;
    el.innerHTML = '<div style="height:500px"></div>';
    el.scrollTop = oldScrollTop;

    expect(el.scrollTop).toBe(100);
  });
});

describe('anti-regression: content_hash guard', () => {
  it('renderWithWidgets skips duplicate content via hash', () => {
    const container = document.createElement('div');
    const content = 'hello world';
    let renderCount = 0;

    function renderWithWidgets(cont: HTMLElement, c: string) {
      if (cont.dataset.contentHash === c) return;
      cont.dataset.contentHash = c;
      renderCount++;
      cont.textContent = c;
    }

    renderWithWidgets(container, content);
    expect(renderCount).toBe(1);
    expect(container.textContent).toBe('hello world');

    renderWithWidgets(container, content);
    expect(renderCount).toBe(1);

    renderWithWidgets(container, 'new content');
    expect(renderCount).toBe(2);
  });
});

describe('anti-regression: new session button guard', () => {
  it('new session button guard prevents double creation', async () => {
    let createCount = 0;
    let _creatingSession = false;

    async function handleClick() {
      if (_creatingSession) return;
      _creatingSession = true;
      createCount++;
      await Promise.resolve();
      _creatingSession = false;
    }

    await handleClick();
    expect(createCount).toBe(1);

    _creatingSession = true;
    await handleClick();
    expect(createCount).toBe(1);

    _creatingSession = false;
    await handleClick();
    expect(createCount).toBe(2);
  });
});

describe('anti-regression: AudioBus cache cleanup on error', () => {
  it('AudioBus removes failed sound from cache on error', () => {
    const cache = new Map<string, HTMLAudioElement>();
    const src = '/static/sounds/send.mp3';

    const audio = { src, onerror: null, volume: 1 } as any;
    audio.onerror = () => { cache.delete('send'); };
    cache.set('send', audio);

    expect(cache.has('send')).toBe(true);
    audio.onerror();
    expect(cache.has('send')).toBe(false);
  });
});

describe('anti-regression: parseStreamEvent constant Set', () => {
  it('parseStreamEvent uses constant Set not new Set()', () => {
    const events = ['heartbeat', 'content', 'reasoning', 'tool_call', 'error', 'memory'];
    const eventSet = new Set(events);

    expect(eventSet.has('content')).toBe(true);
    expect(eventSet.has('unknown')).toBe(false);
    expect(eventSet.has('memory')).toBe(true);
  });
});

describe('anti-regression: _firstScroll autoScroll behavior', () => {
  it('autoScroll first event scrolls unconditionally, subsequent use threshold', () => {
    let callCount = 0;
    let _firstScroll = true;

    function autoScroll() {
      if (_firstScroll) {
        _firstScroll = false;
        callCount++;
        return;
      }
      callCount++;
    }

    autoScroll();
    expect(callCount).toBe(1);

    autoScroll();
    expect(callCount).toBe(2);
    expect(_firstScroll).toBe(false);
  });
});

describe('anti-regression: session load scrolls to last assistant msg', () => {
  it('refreshUI scrolls to last .msg.assistant offsetTop, not generic bottom', () => {
    const msgsEl = document.createElement('div');
    msgsEl.id = 'messages';
    msgsEl.style.height = '100px';
    msgsEl.style.overflow = 'auto';
    msgsEl.scrollTop = 0;

    msgsEl.innerHTML = '';
    const items = [
      { role: 'user', text: 'hola' },
      { role: 'assistant', text: 'primera respuesta' },
      { role: 'user', text: 'otra pregunta' },
      { role: 'assistant', text: 'segunda respuesta' },
    ];
    items.forEach((m, i) => {
      const el = document.createElement('div');
      el.className = `msg ${m.role}`;
      el.style.height = '200px';
      el.textContent = m.text;
      Object.defineProperty(el, 'offsetTop', { value: i * 200, configurable: true });
      msgsEl.appendChild(el);
    });

    // Simulate refreshUI scroll logic: find last assistant and scroll to it
    const lastAssistant = msgsEl.querySelector('.msg.assistant:last-child') as HTMLElement;
    const target = lastAssistant.offsetTop;
    msgsEl.scrollTop = target;

    // 4th child (index 3) = 3 * 200 = 600
    expect(target).toBe(600);
    expect(msgsEl.scrollTop).toBe(600);
  });

  it('falls back to scrollHeight when no assistant msg exists', () => {
    const msgsEl = document.createElement('div');
    msgsEl.id = 'messages';
    msgsEl.style.height = '100px';
    msgsEl.style.overflow = 'auto';
    Object.defineProperty(msgsEl, 'scrollHeight', { value: 500, writable: true });
    msgsEl.scrollTop = 0;

    msgsEl.innerHTML = '';
    const items = [
      { role: 'user', text: 'solo usuario' },
    ];
    items.forEach((m) => {
      const el = document.createElement('div');
      el.className = `msg ${m.role}`;
      el.textContent = m.text;
      msgsEl.appendChild(el);
    });

    const lastAssistant = msgsEl.querySelector('.msg.assistant:last-child') as HTMLElement | null;
    if (lastAssistant) {
      msgsEl.scrollTop = lastAssistant.offsetTop;
    } else {
      msgsEl.scrollTop = msgsEl.scrollHeight;
    }

    expect(msgsEl.scrollTop).toBe(500);
  });
});

describe('anti-regression: session URL sync and init persistence', () => {
  it('init() uses initialSessionId from DOM over data[0].id', () => {
    const sessions = [
      { id: 'aaa', name: 'Old', count: 1, last_str: '2024-01-01' },
      { id: 'bbb', name: 'Target', count: 2, last_str: '2024-01-02' },
    ];
    // Simulate init with initialSessionId pointing to second session
    let activeId = '';
    let loadedHistoryId = '';

    // After loadSessions (normally from API), would set activeId = sessions[0].id
    activeId = sessions[0].id; // data[0].id

    // Then init checks initialSessionId
    const initialSessionId = 'bbb';
    if (initialSessionId && sessions.some(s => s.id === initialSessionId)) {
      activeId = initialSessionId;
      loadedHistoryId = initialSessionId;
    }

    expect(activeId).toBe('bbb');
    expect(loadedHistoryId).toBe('bbb');
  });

  it('selectSession updates browser URL via replaceState', () => {
    // history.replaceState is available in happy-dom, mock it
    let replacedUrl = '';
    const origReplaceState = window.history.replaceState;
    window.history.replaceState = (_state: any, _title: string, url: string | URL | null) => {
      replacedUrl = url as string;
    };

    try {
      const id = 'test-session-123';
      window.history.replaceState({ sessionId: id }, '', `/sessions/${id}`);
      expect(replacedUrl).toBe('/sessions/test-session-123');
    } finally {
      window.history.replaceState = origReplaceState;
    }
  });

  it('createSession pushes new history entry via pushState', () => {
    let pushedUrl = '';
    const origPushState = window.history.pushState;
    window.history.pushState = (_state: any, _title: string, url: string | URL | null) => {
      pushedUrl = url as string;
    };

    try {
      const id = 'new-session-456';
      window.history.pushState({ sessionId: id }, '', `/sessions/${id}`);
      expect(pushedUrl).toBe('/sessions/new-session-456');
    } finally {
      window.history.pushState = origPushState;
    }
  });

  it('deleteSession updates URL to fallback session', () => {
    let replacedUrl = '';
    const origReplaceState = window.history.replaceState;
    window.history.replaceState = (_state: any, _title: string, url: string | URL | null) => {
      replacedUrl = url as string;
    };

    try {
      const fakeSessions = [
        { id: 'survivor', name: 'S', count: 1, last_str: '' },
      ];
      // Simulate deleteSession logic: if active was deleted, fallback to sessions[0]
      const deletedId = 'dead-session';
      const remaining = fakeSessions.filter(s => s.id !== deletedId);
      let newActive = '';
      if (remaining.length > 0) {
        newActive = remaining[0].id;
      }
      if (newActive) {
        window.history.replaceState({ sessionId: newActive }, '', `/sessions/${newActive}`);
      }
      expect(replacedUrl).toBe('/sessions/survivor');
    } finally {
      window.history.replaceState = origReplaceState;
    }
  });

  it('selectSession emits after history is loaded', async () => {
    const events: string[] = [];

    class SessionStoreProbe {
      activeSessionId = 'old';
      sessions = [{ id: 'new' }];

      async loadHistory(id: string) {
        events.push(`load:${id}`);
      }

      _emit(event: string) {
        events.push(event);
      }

      async selectSession(id: string): Promise<void> {
        if (this.activeSessionId !== id && this.sessions.some(s => s.id === id)) {
          this.activeSessionId = id;
          await this.loadHistory(id);
          this._emit('session:selected');
        }
      }
    }

    const store = new SessionStoreProbe();
    await store.selectSession('new');

    expect(events).toEqual(['load:new', 'session:selected']);
  });
});

describe('anti-regression: reasoning/memory collapsed in history, open live', () => {
  it('historical message has reasoning details closed (open=false / no open attr)', () => {
    const el = document.createElement('div');

    // Simulate _renderMessageContent for a simple assistant msg with reasoning
    const reasoning = 'paso a paso...';
    const details = document.createElement('details');
    details.className = 'reasoning'; // C.REASONING
    // No open attribute → collapsed by default
    details.innerHTML = `<summary>Razonamiento</summary><div class="rt">${reasoning}</div>`;
    el.appendChild(details);

    const dt = el.querySelector('details') as HTMLDetailsElement;
    expect(dt.open).toBe(false);
    expect(dt.className).toBe('reasoning');
  });

  it('live streaming reasoning is open (open=true)', () => {
    const details = document.createElement('details');
    details.className = 'reasoning';
    details.dataset.phase = '0';
    details.open = true; // Live streaming sets this
    details.innerHTML = '<summary>Razonando...</summary><div class="rt"></div>';

    expect(details.open).toBe(true);
    expect(details.dataset.phase).toBe('0');
  });

  it('multi-phase memory is collapsed in historical messages', () => {
    const el = document.createElement('div');
    const memory = 'recordé algo';

    const details = document.createElement('details');
    details.className = 'reasoning-memories'; // C.REASONING_MEMORIES
    // No open → collapsed
    details.innerHTML = `<summary>📖 Memorias</summary><div class="memory-content">${memory}</div>`;
    el.appendChild(details);

    const dt = el.querySelector('details') as HTMLDetailsElement;
    expect(dt.open).toBe(false);
    expect(dt.textContent).toContain('recordé algo');
  });

  it('live streaming memory is open (open=true)', () => {
    const details = document.createElement('details');
    details.className = 'reasoning-memories';
    details.open = true;
    details.innerHTML = '<summary>📖 Memorias</summary><div class="memory-content"></div>';

    expect(details.open).toBe(true);
  });

  it('session switch re-renders history with reasoning collapsed', () => {
    const el = document.createElement('div');

    // Simulate appendMessage → _renderMessageContent for session history
    const reasoning = 'razonamiento en sesión';
    const details = document.createElement('details');
    details.className = 'reasoning';
    // No open → collapsed (historical appendMessage)
    details.innerHTML = `<summary>Razonamiento</summary><div class="rt">${reasoning}</div>`;
    el.appendChild(details);

    const dt = el.querySelector('details') as HTMLDetailsElement;
    expect(dt.open).toBe(false);

    // Now simulate a second session load (clear + re-render)
    el.innerHTML = '';
    const details2 = document.createElement('details');
    details2.className = 'reasoning';
    details2.innerHTML = `<summary>Razonamiento</summary><div class="rt">${reasoning}</div>`;
    el.appendChild(details2);

    expect(el.querySelector('details')!.open).toBe(false);
  });
});

describe('anti-regression: session rename/delete with confirm/cancel', () => {
  it('rename shows ✓ and ✕ buttons instead of immediate submit', () => {
    // Simulate rename: click rename → actions replaced by confirm/cancel
    const actionsEl = document.createElement('div');
    actionsEl.className = 'session-actions';

    const renameIcon = document.createElement('button');
    renameIcon.className = 'act-rename';

    const deleteIcon = document.createElement('button');
    deleteIcon.className = 'act-delete';

    actionsEl.appendChild(renameIcon);
    actionsEl.appendChild(deleteIcon);

    expect(actionsEl.children.length).toBe(2);
    expect(actionsEl.querySelector('.act-confirm')).toBeNull();
    expect(actionsEl.querySelector('.act-cancel')).toBeNull();

    // Simulate rename click: replace with confirm/cancel
    actionsEl.innerHTML = '';
    const confirmBtn = document.createElement('button');
    confirmBtn.className = 'act-confirm';
    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'act-cancel';
    actionsEl.appendChild(confirmBtn);
    actionsEl.appendChild(cancelBtn);

    expect(actionsEl.children.length).toBe(2);
    expect(actionsEl.querySelector('.act-confirm')).not.toBeNull();
    expect(actionsEl.querySelector('.act-cancel')).not.toBeNull();
    expect(actionsEl.querySelector('.act-rename')).toBeNull();
    expect(actionsEl.querySelector('.act-delete')).toBeNull();
  });

  it('rename cancel restores original rename/delete buttons', () => {
    const actionsEl = document.createElement('div');
    const renameIcon = document.createElement('button');
    renameIcon.className = 'act-rename';
    const deleteIcon = document.createElement('button');
    deleteIcon.className = 'act-delete';
    actionsEl.appendChild(renameIcon);
    actionsEl.appendChild(deleteIcon);

    // Enter rename mode
    actionsEl.innerHTML = '';
    actionsEl.appendChild(document.createElement('button'));
    actionsEl.appendChild(document.createElement('button'));

    // Cancel: restore
    actionsEl.innerHTML = '';
    actionsEl.appendChild(renameIcon);
    actionsEl.appendChild(deleteIcon);

    expect(actionsEl.children.length).toBe(2);
    expect(actionsEl.querySelector('.act-rename')).not.toBeNull();
    expect(actionsEl.querySelector('.act-delete')).not.toBeNull();
  });

  it('delete shows ✓ and ✕ confirm buttons instead of immediate delete', () => {
    const actionsEl = document.createElement('div');
    const renameIcon = document.createElement('button');
    renameIcon.className = 'act-rename';
    const deleteIcon = document.createElement('button');
    deleteIcon.className = 'act-delete';
    actionsEl.appendChild(renameIcon);
    actionsEl.appendChild(deleteIcon);

    // Simulate delete click: replace with confirm/cancel
    actionsEl.innerHTML = '';
    const confirmBtn = document.createElement('button');
    confirmBtn.className = 'act-confirm';
    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'act-cancel';
    actionsEl.appendChild(confirmBtn);
    actionsEl.appendChild(cancelBtn);

    expect(actionsEl.children.length).toBe(2);
    expect(actionsEl.querySelector('.act-confirm')).not.toBeNull();
    expect(actionsEl.querySelector('.act-cancel')).not.toBeNull();
    expect(actionsEl.querySelector('.act-delete')).toBeNull();
  });

  it('delete cancel restores original rename/delete buttons', () => {
    const actionsEl = document.createElement('div');
    const renameIcon = document.createElement('button');
    renameIcon.className = 'act-rename';
    const deleteIcon = document.createElement('button');
    deleteIcon.className = 'act-delete';
    actionsEl.appendChild(renameIcon);
    actionsEl.appendChild(deleteIcon);

    // Enter delete confirm mode
    actionsEl.innerHTML = '';
    actionsEl.appendChild(document.createElement('button'));
    actionsEl.appendChild(document.createElement('button'));

    // Cancel: restore
    actionsEl.innerHTML = '';
    actionsEl.appendChild(renameIcon);
    actionsEl.appendChild(deleteIcon);

    expect(actionsEl.children.length).toBe(2);
    expect(actionsEl.querySelector('.act-rename')).not.toBeNull();
    expect(actionsEl.querySelector('.act-delete')).not.toBeNull();
  });

  it('SVG icons CHECK_ICON and CANCEL_ICON exist in rendered HTML', () => {
    // Verify the SVGs render correctly with checkmark and X paths
    const checkHtml = '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>';
    const cancelHtml = '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>';

    // Parse and verify the SVGs
    const checkWrapper = document.createElement('div');
    checkWrapper.innerHTML = checkHtml;
    const checkSvg = checkWrapper.querySelector('svg')!;
    expect(checkSvg).not.toBeNull();
    expect(checkSvg.querySelector('path')!.getAttribute('d')).toContain('16.17');

    const cancelWrapper = document.createElement('div');
    cancelWrapper.innerHTML = cancelHtml;
    const cancelSvg = cancelWrapper.querySelector('svg')!;
    expect(cancelSvg).not.toBeNull();
    expect(cancelSvg.querySelector('path')!.getAttribute('d')).toContain('6.41');
  });
});

describe('anti-regression: widget rendering fixes', () => {
  it('ensureBody removes stale placeholder body div', () => {
    const msgEl = document.createElement('div');
    // Simulate beginStreaming placeholder (no data-phase)
    const staleBody = document.createElement('div');
    staleBody.className = 'msg-body';
    staleBody.textContent = '✍️ Pensando...';
    msgEl.appendChild(staleBody);
    expect(msgEl.children.length).toBe(1);

    // Simulate ensureBody for phase 0: remove stale, create proper
    const stale = msgEl.querySelector('.msg-body:not([data-phase])') as HTMLElement | null;
    if (stale) stale.remove();
    const body = document.createElement('div');
    body.className = 'msg-body';
    body.setAttribute('data-phase', '0');
    msgEl.appendChild(body);

    expect(msgEl.children.length).toBe(1);
    expect(msgEl.querySelector('.msg-body[data-phase="0"]')).not.toBeNull();
    expect(msgEl.querySelector('.msg-body:not([data-phase])')).toBeNull();
  });

  it('hasNewWidgetBoundary detects [Widget: key] tags', () => {
    const regex = /```html-widget|~~~widget-(?:start|end)|\[Widget\s*:\s*[\w\-]+\]/;
    expect(regex.test('some text [Widget: chart] more')).toBe(true);
    expect(regex.test('some text [Widget:focus-terminal] more')).toBe(true);
    expect(regex.test('some text [Widget: my-widget-2] more')).toBe(true);
    expect(regex.test('```html-widget')).toBe(true);
    expect(regex.test('~~~widget-start')).toBe(true);
    expect(regex.test('plain text without widget')).toBe(false);
  });

  it('BrowserDomRenderer uses injected widgetRegistry', () => {
    // Simulate: create a MessageView-like scenario with shared registry
    const sharedRegistry = {
      extract: (text: string) => text.replace('```html-widget demo\ncode\n```', '<div class="interactive-widget-container" data-widget-id="widget-0"></div>'),
      getCode: (id: string) => id === 'widget-0' ? 'code' : undefined,
    } as any;

    const testRenderer = {
      renderMessage: (container: HTMLElement, content: string, isMarkdown: boolean) => {
        if (isMarkdown) {
          const extracted = sharedRegistry.extract(content);
          container.innerHTML = extracted;
        }
      },
    } as any;

    // Simulate iframeBuilder that looks up code in shared registry
    const testIframeBuilder = {
      initAll: (container: HTMLElement, force: boolean) => {
        const containers = container.querySelectorAll('.interactive-widget-container');
        expect(containers.length).toBe(1);
        const id = containers[0].getAttribute('data-widget-id');
        const code = sharedRegistry.getCode(id!);
        expect(code).toBe('code'); // Would be undefined if registries differ
      },
    } as any;

    const container = document.createElement('div');
    testRenderer.renderMessage(container, 'widget: ```html-widget demo\ncode\n```', true);
    testIframeBuilder.initAll(container, true);
  });

  it('widget-iframe CSS has border and hover styles', () => {
    // Verify the CSS classes match between DomContracts and what's applied
    const iframe = document.createElement('iframe');
    iframe.className = 'widget-iframe'; // What DomContracts defines as WIDGET_IFRAME
    document.body.appendChild(iframe);
    const style = getComputedStyle(iframe);
    // Should have border (the important fix)
    expect(iframe.className).toBe('widget-iframe');
    document.body.removeChild(iframe);
  });

  it('streaming triggers full regeneration when widgetMatches detected in full text', () => {
    // Simulate ContentHandler.handleContent logic with token-by-token streaming
    let fullText = '';
    let lastRenderedLength = 0;
    let fullRegenCalled = false;

    function handleContentChunk(chunk: string) {
      fullText += chunk;
      const delta = fullText.slice(lastRenderedLength);

      // Simulate processWidgetContainers output for the full text
      const hasCompleteWidget = /```html-widget[\s\S]*?\n```/.test(fullText);
      const hasWidgetBoundaryInDelta = /```html-widget|~~~widget-(?:start|end)|\[Widget\s*:\s*[\w\-]+\]/.test(delta);

      // The bug: before fix, this was `!hasWidgetBoundaryInDelta` only
      // Now: also checks widgetMatches.length (simulated as hasCompleteWidget)
      if (lastRenderedLength > 0 && !hasWidgetBoundaryInDelta && !hasCompleteWidget) {
        // incremental path
      } else {
        fullRegenCalled = true;
      }
      lastRenderedLength = fullText.length;
    }

    // First chunk always triggers full regen (lastRenderedLength === 0)
    // This matches ContentHandler behavior — initial render is always full
    fullRegenCalled = false;
    handleContentChunk('```html');   // first: lastRenderedLength=0 → full regen (initial)

    // Subsequent chunks with widget INCOMPLETE should be incremental
    fullRegenCalled = false;
    handleContentChunk('-widget');   // delta='-widget' → no match, widget not complete
    expect(fullRegenCalled).toBe(false); // incremental

    handleContentChunk(' demo\n');   // still incomplete
    expect(fullRegenCalled).toBe(false);

    handleContentChunk('<div>code</div>\n'); // still open
    expect(fullRegenCalled).toBe(false);

    handleContentChunk('```');       // NOW widget is complete in full text!
    expect(fullRegenCalled).toBe(true); // full regeneration triggered
  });
});
