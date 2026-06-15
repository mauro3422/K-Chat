/** SSE client — connects to the event stream and refreshes UI in real time.

Listens for ``new_message`` events from the server and updates the sidebar
and the current session's message list automatically.
 */

import { ApiClient } from './api-client.js';
import { refreshSidebar } from './sidebar-refresh.js';

var _eventSource = null;
var _currentSessionId = null;

export function setCurrentSessionId(sid) {
  _currentSessionId = sid;
}

export function connect() {
  if (_eventSource) {
    _eventSource.close();
  }

  _eventSource = new EventSource('/api/events/stream');

  _eventSource.addEventListener('message', function(e) {
    try {
      var event = JSON.parse(e.data);
      if (event.type === 'ping') return;

      if (event.type === 'new_message') {
        var sid = event.data && event.data.session_id;
        if (sid) {
          // Refresh sidebar
          refreshSidebar();
          // If this session is currently active, reload messages
          if (sid === _currentSessionId) {
            reloadMessages(sid);
          }
        }
      }
    } catch (err) {
      console.error('SSE error:', err);
    }
  });

  _eventSource.addEventListener('error', function() {
    // Reconnect after 3s on connection loss
    setTimeout(connect, 3000);
  });
}

function reloadMessages(sid) {
  ApiClient.loadMessages(sid)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var messagesDiv = document.getElementById('messages');
      if (!messagesDiv) return;
      import('./message-renderer.js').then(function(mr) {
        var html = mr.renderMessageList(data.messages || [], data.widget_states || {});
        messagesDiv.innerHTML = html;
      });
      import('./markdown-renderer.js').then(function(md) {
        if (typeof md.renderAll === 'function') md.renderAll();
      });
      import('./stream-lifecycle.js').then(function(sl) {
        if (typeof sl.scrollToBottom === 'function') sl.scrollToBottom();
      });
    })
    .catch(function() {});
}

// Don't auto-connect at module load — called explicitly from app.js
// to avoid breaking the page if EventSource fails.
