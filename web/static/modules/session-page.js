import { SessionContext } from './session-context.js';
import { KairosUtils } from './utils.js';
import { KairosMarkdown } from './markdown-renderer.js';
import { ApiClient } from './api-client.js';
import { KairosWidgets } from './widgets/index.js';
import { KairosForm } from './chat-form.js';
import stateManager from './widgets/state-manager.js';

import { refreshSidebar } from './sidebar-refresh.js';

function getNav(deps) {
  if (deps && deps.nav) return deps.nav;
  return {
    location: window.location,
    history: window.history,
    onDomReady: function(cb) { document.addEventListener('DOMContentLoaded', cb); },
    onPopState: function(cb) { window.addEventListener('popstate', cb); },
  };
}

function createActionButton(className, title, label) {
  var button = document.createElement('button');
  button.className = className;
  button.title = title;
  button.textContent = label;
  return button;
}

function escapeHtmlAttr(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function setActionButtons(actions, buttonsHtml, buttons) {
  if (!actions) return;
  if (typeof actions.replaceChildren === 'function') {
    actions.replaceChildren.apply(actions, buttons);
    return;
  }
  if (typeof actions.appendChild === 'function') {
    while (actions.firstChild) {
      actions.removeChild(actions.firstChild);
    }
    for (var i = 0; i < buttons.length; i++) {
      actions.appendChild(buttons[i]);
    }
    return;
  }
  if ('textContent' in actions) {
    actions.textContent = buttonsHtml.replace(/<[^>]+>/g, '');
  }
}

function setMainHtml(main, html) {
  if (!main) return;
  if (typeof document.createElement === 'function') {
    var template = document.createElement('template');
    if (template && 'innerHTML' in template && typeof main.replaceChildren === 'function') {
      template.innerHTML = html;
      main.replaceChildren(template.content.cloneNode(true));
      return;
    }
  }
  main.innerHTML = html;
}

function setPreviewInput(preview, value) {
  if (!preview) return null;
  if (typeof preview.appendChild === 'function') {
    preview.textContent = '';
    var input = document.createElement('input');
    input.className = 'si';
    input.type = 'text';
    input.value = value;
    preview.appendChild(input);
    return input;
  }
  if (typeof preview.textContent !== 'undefined') {
    preview.textContent = '';
  }
  return null;
}

function confirmRename(item, sid) {
  var inp = item.querySelector('.si');
  if (!inp) return;
  var name = inp.value.trim();
  if (!name) { cancelEdit(item); return; }
  ApiClient.renameSession(sid, name).then(function() {
    item.querySelector('.session-preview').textContent = name;
    restoreActions(item);
  }).catch(function(err) { console.error('Rename failed:', err); });
}

function cancelEdit(item) {
  var orig = item.dataset.origName;
  if (orig) { item.querySelector('.session-preview').textContent = orig; }
  restoreActions(item);
  delete item.dataset.origName;
}

function restoreActions(item) {
  var actions = item.querySelector('.session-actions');
  setActionButtons(
    actions,
    '<button class="act-rename" title="Renombrar">&#9998;</button>' +
    '<button class="act-delete" title="Eliminar">&#128465;</button>',
    [
      createActionButton('act-rename', 'Renombrar', '✎'),
      createActionButton('act-delete', 'Eliminar', '🗑')
    ]
  );
}

function bindModelSelect() {
  var select = document.getElementById('model-select');
  if (!select) return;
  select.value = localStorage.getItem('selected_model') || select.value;
  select.addEventListener('change', function() {
    localStorage.setItem('selected_model', select.value);
  });
}

function loadInitialWidgetStates() {
  var meta = document.getElementById('messages-metadata');
  if (meta) {
    try {
      stateManager.loadFromJSON(JSON.parse(meta.getAttribute('data-widget-states') || '{}'));
    } catch(e) {
      console.error('Error parsing initial widgetStates:', e);
    }
  }
}

function initSessionPage(deps) {
  var nav = getNav(deps);
  loadInitialWidgetStates();
  document.addEventListener('htmx:afterSwap', function() {
    KairosUtils.scrollToBottom();
  });
  nav.onDomReady(bindModelSelect);
  nav.onDomReady(function() {
    if (nav.location.pathname.startsWith('/sessions/')) {
      loadSession(SessionContext.getSessionId(), deps);
    }
  });
  document.addEventListener('click', function(e) {
    var item = e.target.closest('.session-item');
    if (!item) return;
    var sid = item.dataset.sid;
    var targetIsInput = e.target && (
      e.target.tagName === 'INPUT' ||
      e.target.tagName === 'TEXTAREA' ||
      (e.target.classList && e.target.classList.contains('si'))
    );
    if (targetIsInput) {
      return;
    }
    if (e.target.classList.contains('act-rename')) {
      var preview = item.querySelector('.session-preview');
      item.dataset.origName = preview.textContent;
      var input = setPreviewInput(preview, item.dataset.origName);
      var renameActions = item.querySelector('.session-actions');
      setActionButtons(
        renameActions,
        '<button class="act-confirm act-ok" title="Guardar">&#10003;</button>' +
        '<button class="act-cancel" title="Cancelar">&#10005;</button>',
        [
          createActionButton('act-confirm act-ok', 'Guardar', '✓'),
          createActionButton('act-cancel', 'Cancelar', '✕')
        ]
      );
      var inp = input || (preview.querySelector ? preview.querySelector('.si') : null);
      if (inp) {
        if (typeof inp.focus === 'function') { inp.focus(); }
        if (typeof inp.select === 'function') { inp.select(); }
        inp.onkeydown = function(ev) {
          if (ev.key === 'Enter') { confirmRename(item, sid); }
          if (ev.key === 'Escape') { cancelEdit(item); }
        };
      }
      return;
    }
    if (e.target.classList.contains('act-delete')) {
      item.dataset.origHTML = item.outerHTML;
      item.querySelector('.session-preview').textContent = 'Eliminar?';
      var deleteActions = item.querySelector('.session-actions');
      setActionButtons(
        deleteActions,
        '<button class="act-confirm act-del" title="Confirmar">&#10003;</button>' +
        '<button class="act-cancel" title="Cancelar">&#10005;</button>',
        [
          createActionButton('act-confirm act-del', 'Confirmar', '✓'),
          createActionButton('act-cancel', 'Cancelar', '✕')
        ]
      );
      return;
    }
    if (e.target.classList.contains('act-cancel')) {
      if (item.dataset.origHTML) { item.outerHTML = item.dataset.origHTML; }
      else { cancelEdit(item); }
      return;
    }
    if (e.target.classList.contains('act-confirm') && item.querySelector('.act-del')) {
      ApiClient.deleteSession(sid).then(function() {
        if (SessionContext.getSessionId() === sid) { nav.location.href = '/'; }
        else { item.remove(); }
      }).catch(function(err) { console.error('Delete failed:', err); });
      return;
    }
    if (e.target.classList.contains('act-confirm') && item.querySelector('.act-ok')) {
      confirmRename(item, sid);
      return;
    }
    loadSession(sid);
  });
  nav.onPopState(function(e) { if (e.state && e.state.sid) { SessionContext.setSessionId(e.state.sid); } });
}

function loadSession(sid, deps) {
  var nav = getNav(deps);
  SessionContext.setSessionId(sid);
  nav.history.replaceState({sid: sid}, '', '/sessions/' + sid);
  if (typeof KairosWidgets.reset === 'function') {
    KairosWidgets.reset();
  }
  if (typeof KairosForm.reset === 'function') {
    KairosForm.reset();
  }
  ApiClient.loadMessages(sid)
    .then(function(r) { return r.text(); })
    .then(function(h) {
      var main = document.getElementById('main');
      if (main) {
        setMainHtml(main, h);
        var meta = document.getElementById('messages-metadata');
        if (meta) {
          try {
            stateManager.loadFromJSON(JSON.parse(meta.getAttribute('data-widget-states') || '{}'));
          } catch(e) {
            console.error('Error parsing widgetStates metadata:', e);
            stateManager.clear();
          }
        } else {
          stateManager.clear();
        }
        KairosMarkdown.renderAll();
      }
    })
    .catch(function(err) { console.error('Failed to load messages:', err); });
}

export const KairosSessionPage = {
  refreshSidebar,
  confirmRename,
  cancelEdit,
  restoreActions,
  loadSession,
  initSessionPage
};

export { loadSession, initSessionPage };
