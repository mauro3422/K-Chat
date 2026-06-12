/* eslint-disable no-redeclare, no-unused-vars */

import { SessionContext } from './modules/session-context.js';

function refreshSidebar() {
  var urlBuilder = SessionContext.createSessionUrlBuilder();
  fetch(urlBuilder.sidebar()).then(function(r){ return r.text(); }).then(function(h){
    document.getElementById('session-list').innerHTML = h;
  }).catch(function(err) { console.error('Sidebar refresh failed:', err); });
}

function confirmRename(item, sid) {
  var inp = item.querySelector('.si');
  if (!inp) return;
  var name = inp.value.trim();
  if (!name) { cancelEdit(item); return; }
  fetch('/sessions/' + sid + '/rename', {method:'POST',
    headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body:'name='+encodeURIComponent(name)}).then(function() {
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

export const KairosSession = { refreshSidebar, confirmRename, cancelEdit, restoreActions };

// Backwards-compatible globals for HTML onclick handlers
window.KairosSession = KairosSession;
window.refreshSidebar = KairosSession.refreshSidebar;


document.addEventListener('htmx:afterSwap', function() {
  KairosUtils.scrollToBottom();
  if (typeof debugVisible !== 'undefined' && debugVisible) { toggleDebug(); }
});

document.addEventListener('click', function(e) {
  var item = e.target.closest('.session-item');
  if (!item) return;
  var sid = item.dataset.sid;

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
      if (ev.key === 'Enter') { KairosSession.confirmRename(item, sid); }
      if (ev.key === 'Escape') { KairosSession.cancelEdit(item); }
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
    else { KairosSession.cancelEdit(item); }
    return;
  }

  if (e.target.classList.contains('act-confirm') && item.querySelector('.act-del')) {
    fetch('/sessions/' + sid + '/delete', {method:'POST'}).then(function() {
      if (SessionContext.getSessionId() === sid) { window.location.href = '/'; }
      else { item.remove(); }
    }).catch(function(err) { console.error('Delete failed:', err); });
    return;
  }

  if (e.target.classList.contains('act-confirm') && item.querySelector('.act-ok')) {
    KairosSession.confirmRename(item, sid);
    return;
  }
});

window.onpopstate = function(e) { if (e.state && e.state.sid) { SessionContext.setSessionId(e.state.sid); globalThis.sessionId = e.state.sid; } };
