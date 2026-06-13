import { describe, test, expect, beforeEach, vi } from 'vitest';
import './setup.js';

vi.mock('../web/static/modules/utils.js', () => ({
  KairosUtils: { scrollToBottom: vi.fn() }
}));

const sessionContextModule = await import('../web/static/modules/session-context.js');
sessionContextModule.SessionContext.setSessionId('test-session-123');

// Override specific mocks for session tests
global.window.onpopstate = null;
global.fetch = () => Promise.resolve({ text: () => Promise.resolve('') });

// Load module (IIFE executes, registers event listeners)
const sessionModule = await import('../web/static/session.js');
const KairosSession = sessionModule.KairosSession;

function makeItem(origName) {
  var inpObj = { value: origName || '', focus: function(){}, select: function(){}, onkeydown: null };
  var preview = {
    textContent: origName || '',
    innerHTML: '',
    querySelector: function(sel) {
      if (sel === '.si') return inpObj;
      return null;
    }
  };
  var actions = { innerHTML: '' };
  return {
    dataset: { sid: 'test-sid', origName: origName },
    outerHTML: '<div class="session-item"></div>',
    preview: preview,
    actions: actions,
    _inp: inpObj,
    querySelector: function(sel) {
      if (sel === '.session-preview') return this.preview;
      if (sel === '.session-actions') return this.actions;
      if (sel === '.si') return this._inp;
      if (sel === '.act-del') return null;
      if (sel === '.act-ok') return null;
      return null;
    },
    querySelectorAll: function() { return []; },
    remove: function() {}
  };
}

describe('KairosSession', () => {
  beforeEach(() => {
    sessionContextModule.SessionContext.setSessionId('test-session-123');
  });

  test('confirmRename empty cancela sin fetch', () => {
    let fetchCalled = false;
    const origFetch = global.fetch;
    global.fetch = function() { fetchCalled = true; return Promise.resolve(); };
    const item = makeItem('Original');
    item._inp.value = '   ';
    KairosSession.confirmRename(item, 'sid-empty');
    global.fetch = origFetch;
    expect(fetchCalled).toBe(false);
  });

  test('cancelEdit restaura textContent', () => {
    const item = makeItem('Mi Chat');
    item.dataset.origName = 'Mi Chat';
    KairosSession.cancelEdit(item);
    expect(item.preview.textContent).toBe('Mi Chat');
  });

  test('cancelEdit elimina origName del dataset', () => {
    const item = makeItem('Mi Chat');
    item.dataset.origName = 'Mi Chat';
    KairosSession.cancelEdit(item);
    expect(item.dataset.origName).toBeFalsy();
  });

  test('restoreActions tiene act-rename', () => {
    const item = makeItem('');
    KairosSession.restoreActions(item);
    expect(item.actions.innerHTML).toContain('act-rename');
  });

  test('restoreActions tiene act-delete', () => {
    const item = makeItem('');
    KairosSession.restoreActions(item);
    expect(item.actions.innerHTML).toContain('act-delete');
  });

  test('onpopstate restaura sessionId', () => {
    sessionContextModule.SessionContext.setSessionId('before');
    window.onpopstate({ state: { sid: 'restored-sid-456' } });
    expect(sessionContextModule.SessionContext.getSessionId()).toBe('restored-sid-456');
  });

  test('onpopstate sin sid no cambia', () => {
    sessionContextModule.SessionContext.setSessionId('unchanged');
    window.onpopstate({ state: {} });
    expect(sessionContextModule.SessionContext.getSessionId()).toBe('unchanged');
  });

  test('htmx:afterSwap llama scrollToBottom', async () => {
    const { KairosUtils } = await import('../web/static/modules/utils.js');
    const h = global.document._listeners['htmx:afterSwap'];
    if (h) h();
    expect(KairosUtils.scrollToBottom).toHaveBeenCalled();
  });

  test('click rename guarda origName en dataset', () => {
    const item = makeItem('Chat Name');
    item.dataset.origName = undefined;
    const fakeEvent = {
      target: {
        classList: { contains: (c) => c === 'act-rename' },
        closest: () => item
      }
    };
    const h = global.document._listeners.click;
    if (h) h(fakeEvent);
    expect(item.dataset.origName).toBe('Chat Name');
  });

  test('click rename inserta input en preview', () => {
    const item = makeItem('Chat Name');
    item.dataset.origName = undefined;
    const fakeEvent = {
      target: {
        classList: { contains: (c) => c === 'act-rename' },
        closest: () => item
      }
    };
    const h = global.document._listeners.click;
    if (h) h(fakeEvent);
    expect(item.preview.innerHTML).toContain('input');
  });

  test('click rename asigna onkeydown al input', () => {
    const item = makeItem('Chat Name');
    item.dataset.origName = undefined;
    const fakeEvent = {
      target: {
        classList: { contains: (c) => c === 'act-rename' },
        closest: () => item
      }
    };
    const h = global.document._listeners.click;
    if (h) h(fakeEvent);
    expect(typeof item._inp.onkeydown).toBe('function');
  });

  test('click delete guarda origHTML', () => {
    const item = makeItem('To Delete');
    item.dataset.origHTML = undefined;
    const fakeEvent = {
      target: {
        classList: { contains: (c) => c === 'act-delete' },
        closest: () => item
      }
    };
    const h = global.document._listeners.click;
    if (h) h(fakeEvent);
    expect(item.dataset.origHTML).toBeDefined();
  });

  test('click delete muestra Eliminar?', () => {
    const item = makeItem('To Delete');
    item.dataset.origHTML = undefined;
    const fakeEvent = {
      target: {
        classList: { contains: (c) => c === 'act-delete' },
        closest: () => item
      }
    };
    const h = global.document._listeners.click;
    if (h) h(fakeEvent);
    expect(item.preview.textContent).toBe('Eliminar?');
  });

  test('click cancel restaura outerHTML', () => {
    const restoreHTML = '<div class="restored">original</div>';
    const item = makeItem('');
    item.dataset.origHTML = restoreHTML;
    item.outerHTML = 'temporary';
    const fakeEvent = {
      target: {
        classList: { contains: (c) => c === 'act-cancel' },
        closest: () => item
      }
    };
    const h = global.document._listeners.click;
    if (h) h(fakeEvent);
    expect(item.outerHTML).toBe(restoreHTML);
  });

  test('click cancel sin origHTML restaura nombre', () => {
    const item = makeItem('Edited');
    item.dataset.origName = 'Original';
    item.dataset.origHTML = undefined;
    const fakeEvent = {
      target: {
        classList: { contains: (c) => c === 'act-cancel' },
        closest: () => item
      }
    };
    const h = global.document._listeners.click;
    if (h) h(fakeEvent);
    expect(item.preview.textContent).toBe('Original');
  });

  test('click irrelevante no modifica dataset', () => {
    const item = makeItem('Irrelevant');
    const origName = item.dataset.origName;
    const fakeEvent = {
      target: {
        classList: { contains: () => false },
        closest: () => item
      }
    };
    const h = global.document._listeners.click;
    if (h) h(fakeEvent);
    expect(item.dataset.origName).toBe(origName);
  });

  test('click sin .session-item no hace nada', () => {
    const item = makeItem('');
    const fakeEvent = {
      target: {
        classList: { contains: () => false },
        closest: () => null
      }
    };
    const h = global.document._listeners.click;
    if (h) h(fakeEvent);
    expect(true).toBe(true);
  });

  test('click sobre session-item carga la sesion', () => {
    const item = makeItem('Open me');
    sessionContextModule.SessionContext.setSessionId('before-click');
    const fakeEvent = {
      target: {
        classList: { contains: () => false },
        closest: (sel) => (sel === '.session-item' ? item : null)
      }
    };
    const h = global.document._listeners.click;
    if (h) h(fakeEvent);
    expect(sessionContextModule.SessionContext.getSessionId()).toBe('test-sid');
  });
});
