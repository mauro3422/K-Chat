/** SSE client — connects to the event stream and refreshes UI in real time.

Listens for ``new_message`` events from the server and updates the sidebar
and the current session's message list automatically.
 */

import { ApiClient } from './api-client.js';
import { refreshSidebar } from './sidebar-refresh.js';

var _eventSource = null;
var _currentSessionId = null;

// Flag to avoid race between SSE and initial loadSession
// loadSession sets this to true; SSE checks it before writing
var _loadingSession = false;

export function setLoadingSession(v) {
  _loadingSession = v;
}

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
          // If the message is NOT for the current session, mark sidebar
          if (sid !== _currentSessionId) {
            markSessionUnread(sid);
          }
          // Always refresh sidebar (sorts, updates metadata)
          refreshSidebar().then(function() {
            // After sidebar refresh, re-apply unread marks
            restoreUnreadMarks();
          });
          // Only reload messages if this session is active AND not currently loading
          if (sid === _currentSessionId && !_loadingSession) {
            reloadMessages(sid);
          }
        }
      }
    } catch (err) {
      console.error('SSE error:', err);
    }
  });

  _eventSource.addEventListener('error', function() {
    // Browser auto-reconnects EventSource natively.
    console.warn('SSE connection lost (browser will auto-reconnect)');
  });
}

function reloadMessages(sid) {
  ApiClient.loadMessages(sid)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var messagesDiv = document.getElementById('messages');
      if (!messagesDiv) return;
      return import('./message-renderer.js').then(function(mr) {
        var html = mr.renderMessageList(data.messages || [], data.widget_states || {});
        messagesDiv.innerHTML = html;
        return Promise.all([
          import('./markdown-renderer.js'),
          import('./stream-lifecycle.js'),
        ]);
      });
    })
    .then(function(modules) {
      if (!modules) return;
      if (typeof modules[0].renderAll === 'function') modules[0].renderAll();
      if (typeof modules[1].scrollToBottom === 'function') modules[1].scrollToBottom();
    })
    .catch(function(err) {
      console.error('SSE reloadMessages failed:', err);
    });
}

// ─── Unread session indicators ─────────────────────────────────────
var _unreadSessions = {};

function markSessionUnread(sid) {
  _unreadSessions[sid] = true;
}

function restoreUnreadMarks() {
  for (var sid in _unreadSessions) {
    if (_unreadSessions.hasOwnProperty(sid)) {
      var el = document.querySelector('.session-item[data-sid="' + sid + '"]');
      if (el) el.classList.add('has-new');
    }
  }
}

export function clearUnreadMark(sid) {
  delete _unreadSessions[sid];
  var el = document.querySelector('.session-item[data-sid="' + sid + '"]');
  if (el) el.classList.remove('has-new');
}

// Don't auto-connect at module load — called explicitly from app.js
// to avoid breaking the page if EventSource fails.
