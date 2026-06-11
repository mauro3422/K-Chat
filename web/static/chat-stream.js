import { SessionContext } from './modules/session-context.js';
import stateManager from './modules/widgets/state-manager.js';

stateManager.loadFromJSON({});

(function loadInitialWidgetStates() {
  var meta = document.getElementById('messages-metadata');
  if (meta) {
    try {
      stateManager.loadFromJSON(JSON.parse(meta.getAttribute('data-widget-states') || '{}'));
    } catch(e) {
      console.error('Error parsing initial widgetStates:', e);
    }
  }
})();

// sessionId is set by chat.html template as a global var before this script loads

window.retryLastMessage = function() { KairosForm.retry(); };
window.escHtml = function(s) { return KairosUtils.escHtml(s); };

KairosWidgets.startMessageHandler();
KairosForm.init();

export function loadSession(sid) {
  SessionContext.setSessionId(sid);
  globalThis.sessionId = sid;
  window.history.replaceState({sid: sid}, '', '/sessions/' + sid);

  if (window.KairosWidgets && typeof KairosWidgets.reset === 'function') {
    KairosWidgets.reset();
  }
  if (window.KairosForm && typeof KairosForm.reset === 'function') {
    KairosForm.reset();
  }

  fetch('/sessions/' + sid + '/messages')
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

window.loadSession = loadSession;

document.addEventListener('DOMContentLoaded', function() {
  if (window.location.pathname.startsWith('/sessions/')) {
    window.loadSession(SessionContext.getSessionId());
  }
});
