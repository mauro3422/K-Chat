import { SessionContext } from './session-context.js';
import { KairosUtils } from './utils.js';
import { KairosMarkdown } from './markdown-renderer.js';
import { ApiClient } from './api-client.js';
import { KairosWidgets } from './widgets/index.js';
import { KairosForm } from './chat-form.js';
import stateManager from './widgets/state-manager.js';

function refreshSidebar() {
  ApiClient.sidebar().then(function(h){
    document.getElementById('session-list').innerHTML = h;
  }).catch(function(err) { console.error('Sidebar refresh failed:', err); });
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
  item.querySelector('.session-actions').innerHTML =
    '<button class="act-rename" title="Renombrar">&#9998;</button>' +
    '<button class="act-delete" title="Eliminar">&#128465;</button>';
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

function initSessionPage() {
  loadInitialWidgetStates();
  document.addEventListener('htmx:afterSwap', function() {
    KairosUtils.scrollToBottom();
  });
  document.addEventListener('DOMContentLoaded', bindModelSelect);
  document.addEventListener('DOMContentLoaded', function() {
    if (window.location.pathname.startsWith('/sessions/')) {
      loadSession(SessionContext.getSessionId());
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
      preview.innerHTML = '<input class="si" type="text" value="' + item.dataset.origName.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;') + '">';
      item.querySelector('.session-actions').innerHTML =
        '<button class="act-confirm act-ok" title="Guardar">&#10003;</button>' +
        '<button class="act-cancel" title="Cancelar">&#10005;</button>';
      var inp = preview.querySelector('.si');
      inp.focus(); inp.select();
      inp.onkeydown = function(ev) {
        if (ev.key === 'Enter') { confirmRename(item, sid); }
        if (ev.key === 'Escape') { cancelEdit(item); }
      };
      return;
    }
    if (e.target.classList.contains('act-delete')) {
      item.dataset.origHTML = item.outerHTML;
      item.querySelector('.session-preview').textContent = 'Eliminar?';
      item.querySelector('.session-actions').innerHTML =
        '<button class="act-confirm act-del" title="Confirmar">&#10003;</button>' +
        '<button class="act-cancel" title="Cancelar">&#10005;</button>';
      return;
    }
    if (e.target.classList.contains('act-cancel')) {
      if (item.dataset.origHTML) { item.outerHTML = item.dataset.origHTML; }
      else { cancelEdit(item); }
      return;
    }
    if (e.target.classList.contains('act-confirm') && item.querySelector('.act-del')) {
      ApiClient.deleteSession(sid).then(function() {
        if (SessionContext.getSessionId() === sid) { window.location.href = '/'; }
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
  window.addEventListener('popstate', function(e) { if (e.state && e.state.sid) { SessionContext.setSessionId(e.state.sid); } });
}

function loadSession(sid) {
  SessionContext.setSessionId(sid);
  window.history.replaceState({sid: sid}, '', '/sessions/' + sid);
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
        main.innerHTML = h;
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
