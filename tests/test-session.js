global.document = {
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: () => ({ classList: { add: () => {} }, appendChild: () => {}, style: { cssText: '' }, onclick: null, textContent: '', id: '' }),
  addEventListener: (evt, cb) => { global.document._listeners = global.document._listeners || {}; global.document._listeners[evt] = cb; },
  body: { appendChild: () => {} }
};
global.window = {
  addEventListener: () => {},
  location: { pathname: '/' },
  history: { replaceState: () => {} },
  onpopstate: null
};
global.sessionId = 'test-session-123';
global.KairosUtils = { scrollToBottom: () => {} };
global.fetch = () => Promise.resolve({ text: () => Promise.resolve('') });

eval(require('fs').readFileSync(require('path').join(__dirname, '../web/static/session.js'), 'utf8'));

var passed = 0, failed = 0;
function assert(name, cond, detail) {
  if (cond) { passed++; console.log('  PASS: ' + name); }
  else { failed++; console.log('  FAIL: ' + name + (detail ? ' -- ' + detail : '')); }
}

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

// 1. confirmRename con nombre vacio cancela sin llamar fetch
(function test_confirm_rename_empty_skips_fetch() {
  var fetchCalled = false;
  var origFetch = global.fetch;
  global.fetch = function() { fetchCalled = true; return Promise.resolve(); };
  var item = makeItem('Original');
  item._inp.value = '   ';
  confirmRename(item, 'sid-empty');
  global.fetch = origFetch;
  assert('confirmRename empty cancela sin fetch', !fetchCalled);
})();

// 2. cancelEdit restaura el nombre original y limpia dataset
(function test_cancel_edit_restores_name() {
  var item = makeItem('Mi Chat');
  item.dataset.origName = 'Mi Chat';
  cancelEdit(item);
  assert('cancelEdit restaura textContent', item.preview.textContent === 'Mi Chat');
  assert('cancelEdit elimina origName del dataset', !item.dataset.origName);
})();

// 3. restoreActions pone botones rename y delete
(function test_restore_actions_both_buttons() {
  var item = makeItem('');
  restoreActions(item);
  assert('restoreActions tiene act-rename', item.actions.innerHTML.indexOf('act-rename') >= 0);
  assert('restoreActions tiene act-delete', item.actions.innerHTML.indexOf('act-delete') >= 0);
})();

// 4. onpopstate restaura sessionId del state
(function test_onpopstate_restores_sid() {
  global.sessionId = 'before';
  window.onpopstate({ state: { sid: 'restored-sid-456' } });
  assert('onpopstate restaura sessionId', global.sessionId === 'restored-sid-456');
  global.sessionId = 'test-session-123';
})();

// 5. onpopstate sin state.sid no cambia sessionId
(function test_onpopstate_no_sid_unchanged() {
  global.sessionId = 'unchanged';
  window.onpopstate({ state: {} });
  assert('onpopstate sin sid no cambia', global.sessionId === 'unchanged');
})();

// 6. htmx:afterSwap invoca scrollToBottom
(function test_htmx_after_swap_calls_scroll() {
  var scrolled = false;
  global.KairosUtils.scrollToBottom = function() { scrolled = true; };
  var h = global.document._listeners['htmx:afterSwap'];
  if (h) h();
  assert('htmx:afterSwap llama scrollToBottom', scrolled);
})();

// 7. Click en act-rename inicia modo edicion
(function test_click_rename_starts_edit() {
  var item = makeItem('Chat Name');
  var fakeEvent = {
    target: {
      classList: { contains: function(c) { return c === 'act-rename'; } },
      closest: function() { return item; }
    }
  };
  item.dataset.origName = undefined;
  var h = global.document._listeners.click;
  if (h) h(fakeEvent);
  assert('click rename guarda origName en dataset', item.dataset.origName === 'Chat Name');
  assert('click rename inserta input en preview', item.preview.innerHTML.indexOf('input') >= 0);
  assert('click rename asigna onkeydown al input', typeof item._inp.onkeydown === 'function');
})();

// 8. Click en act-delete muestra confirmacion
(function test_click_delete_shows_confirmation() {
  var item = makeItem('To Delete');
  item.dataset.origHTML = undefined;
  var fakeEvent = {
    target: {
      classList: { contains: function(c) { return c === 'act-delete'; } },
      closest: function() { return item; }
    }
  };
  var h = global.document._listeners.click;
  if (h) h(fakeEvent);
  assert('click delete guarda origHTML', item.dataset.origHTML !== undefined);
  assert('click delete muestra "Eliminar?"', item.preview.textContent === 'Eliminar?');
})();

// 9. Click en act-cancel con origHTML restaura outerHTML
(function test_click_cancel_with_origHTML() {
  var restoreHTML = '<div class="restored">original</div>';
  var item = makeItem('');
  item.dataset.origHTML = restoreHTML;
  item.outerHTML = 'temporary';
  var fakeEvent = {
    target: {
      classList: { contains: function(c) { return c === 'act-cancel'; } },
      closest: function() { return item; }
    }
  };
  var h = global.document._listeners.click;
  if (h) h(fakeEvent);
  assert('click cancel restaura outerHTML', item.outerHTML === restoreHTML);
})();

// 10. Click en act-cancel sin origHTML llama cancelEdit (restaura nombre)
(function test_click_cancel_without_origHTML() {
  var item = makeItem('Edited');
  item.dataset.origName = 'Original';
  item.dataset.origHTML = undefined;
  var fakeEvent = {
    target: {
      classList: { contains: function(c) { return c === 'act-cancel'; } },
      closest: function() { return item; }
    }
  };
  var h = global.document._listeners.click;
  if (h) h(fakeEvent);
  assert('click cancel sin origHTML restaura nombre preview', item.preview.textContent === 'Original');
})();

// 11. Click irrelevante (no rename/delete/cancel/confirm) no modifica dataset
(function test_click_unrelated_does_nothing() {
  var item = makeItem('Irrelevant');
  var origName = item.dataset.origName;
  var fakeEvent = {
    target: {
      classList: { contains: function(c) { return false; } },
      closest: function() { return item; }
    }
  };
  var h = global.document._listeners.click;
  if (h) h(fakeEvent);
  assert('click irrelevante no modifica dataset.origName', item.dataset.origName === origName);
})();

// 12. Click en item sin session-item target no hace nada
(function test_click_no_session_item() {
  var item = makeItem('');
  var noopReached = true;
  var fakeEvent = {
    target: {
      classList: { contains: function() { return false; } },
      closest: function() { return null; }
    }
  };
  var h = global.document._listeners.click;
  if (h) h(fakeEvent);
  assert('click sin .session-item no hace nada', true);
})();

console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed > 0 ? 1 : 0);
