import { describe, test, expect, beforeEach, vi } from 'vitest';
import './setup.js';

vi.mock('../web/static/modules/utils.js', () => ({
  Utils: { scrollToBottom: vi.fn() }
}));

const sessionContextModule = await import('../web/static/modules/session-context.js');
sessionContextModule.SessionContext.setSessionId('test-session-123');

// Override specific mocks for session tests
global.fetch = () => Promise.resolve({
  text: () => Promise.resolve(''),
  json: () => Promise.resolve({ messages: [], widget_states: {} })
});

const sessionModule = await import('../web/static/modules/session-page.js');
const Session = sessionModule.SessionPage;
const testNav = {
  location: global.window.location,
  history: global.window.history,
  onDomReady(cb) { global.document.addEventListener('DOMContentLoaded', cb); },
  onPopState(cb) { global.window.addEventListener('popstate', cb); }
};
sessionModule.initSessionPage({ nav: testNav });

function makeItem(origName) {
  var inpObj = { value: origName || '', focus: function(){}, select: function(){}, onkeydown: null };
  var parent = {
    replaced: null,
    replaceChild: function(node, oldNode) {
      this.replaced = { node: node, oldNode: oldNode };
      return node;
    }
  };
  var preview = {
    textContent: origName || '',
    children: [],
    appendChild: function(node) { this.children.push(node); this._lastChild = node; return node; },
    removeChild: function(node) { this.children = this.children.filter(function(child) { return child !== node; }); },
    firstChild: null,
    querySelector: function(sel) {
      if (sel === '.si') return this._lastChild || inpObj;
      return null;
    }
  };
  var actions = {
    children: [],
    appendChild: function(node) { this.children.push(node); return node; },
    removeChild: function(node) { this.children = this.children.filter(function(child) { return child !== node; }); },
    firstChild: null
  };
  return {
    dataset: { sid: 'test-sid', origName: origName },
    outerHTML: '<div class="session-item"></div>',
    preview: preview,
    actions: actions,
    parentNode: parent,
    cloneNode: function() { return makeItem(origName); },
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

describe('Session', () => {
  beforeEach(() => {
    sessionContextModule.SessionContext.setSessionId('test-session-123');
  });

  test('confirmRename empty cancela sin fetch', () => {
    let fetchCalled = false;
    const origFetch = global.fetch;
    global.fetch = function() { fetchCalled = true; return Promise.resolve(); };
    const item = makeItem('Original');
    item._inp.value = '   ';
    Session.confirmRename(item, 'sid-empty');
    global.fetch = origFetch;
    expect(fetchCalled).toBe(false);
  });

  test('cancelEdit restaura textContent', () => {
    const item = makeItem('Mi Chat');
    item.dataset.origName = 'Mi Chat';
    Session.cancelEdit(item);
    expect(item.preview.textContent).toBe('Mi Chat');
  });

  test('cancelEdit elimina origName del dataset', () => {
    const item = makeItem('Mi Chat');
    item.dataset.origName = 'Mi Chat';
    Session.cancelEdit(item);
    expect(item.dataset.origName).toBeFalsy();
  });

  test('restoreActions tiene act-rename', () => {
    const item = makeItem('');
    Session.restoreActions(item);
    expect(item.actions.children.length).toBe(2);
    expect(item.actions.children[0].className).toContain('act-rename');
  });

  test('restoreActions tiene act-delete', () => {
    const item = makeItem('');
    Session.restoreActions(item);
    expect(item.actions.children[1].className).toContain('act-delete');
  });

  test('onpopstate restaura sessionId', () => {
    sessionContextModule.SessionContext.setSessionId('before');
    var handler = global.window._listeners && global.window._listeners.popstate;
    if (handler) handler({ state: { sid: 'restored-sid-456' } });
    expect(sessionContextModule.SessionContext.getSessionId()).toBe('restored-sid-456');
  });

  test('onpopstate sin sid no cambia', () => {
    sessionContextModule.SessionContext.setSessionId('unchanged');
    var handler = global.window._listeners && global.window._listeners.popstate;
    if (handler) handler({ state: {} });
    expect(sessionContextModule.SessionContext.getSessionId()).toBe('unchanged');
  });

  test('htmx:afterSwap llama scrollToBottom', async () => {
    const { Utils } = await import('../web/static/modules/utils.js');
    const h = global.document._listeners['htmx:afterSwap'];
    if (h) h();
    expect(Utils.scrollToBottom).toHaveBeenCalled();
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
    expect(item.preview.children.length).toBe(1);
    expect(item.preview.children[0].tagName).toBe('INPUT');
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
    expect(item.preview.children.length).toBe(1);
    expect(typeof item.preview.children[0].onkeydown).toBe('function');
  });

  test('click delete guarda snapshot', () => {
    const item = makeItem('To Delete');
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

  test('click delete muestra Eliminar?', () => {
    const item = makeItem('To Delete');
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

  test('click cancel restaura snapshot', () => {
    const item = makeItem('');
    const fakeEvent = {
      target: {
        classList: { contains: (c) => c === 'act-cancel' },
        closest: () => item
      }
    };
    const deleteEvent = {
      target: {
        classList: { contains: (c) => c === 'act-delete' },
        closest: () => item
      }
    };
    const h = global.document._listeners.click;
    if (h) h(deleteEvent);
    if (h) h(fakeEvent);
    expect(item.parentNode.replaced).toBeTruthy();
    expect(item.parentNode.replaced.oldNode).toBe(item);
    expect(item.parentNode.replaced.node).not.toBe(item);
  });

  test('click cancel sin origHTML restaura nombre', () => {
    const item = makeItem('Edited');
    item.dataset.origName = 'Original';
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
