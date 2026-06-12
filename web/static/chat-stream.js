import { SessionContext } from './modules/session-context.js';
import stateManager from './modules/widgets/state-manager.js';
import { KairosForm } from './modules/chat-form.js';
import { KairosWidgets, startMessageHandler } from './modules/widgets/index.js';
import { KairosMarkdown } from './modules/markdown-renderer.js';

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

startMessageHandler();
KairosForm.init();

export function loadSession(sid) {
  SessionContext.setSessionId(sid);
  globalThis.sessionId = sid;
  window.history.replaceState({sid: sid}, '', '/sessions/' + sid);

  if (typeof KairosWidgets.reset === 'function') {
    KairosWidgets.reset();
  }
  if (typeof KairosForm.reset === 'function') {
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
