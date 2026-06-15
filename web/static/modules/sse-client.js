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

      var sid = event.data && event.data.session_id;

      // ── Token-level events (live streaming) ──────────────────────
      if (event.type === 'token:reasoning' && sid === _currentSessionId) {
        showLiveIndicator('reasoning');
        return;
      }
      if (event.type === 'token:content' && sid === _currentSessionId) {
        showLiveIndicator('content');
        return;
      }
      if (event.type === 'tool_call' && sid === _currentSessionId) {
        addLiveTool(event.data);
        return;
      }

      // ── Full message reload ──────────────────────────────────────
      if (event.type === 'new_message') {
        if (sid) {
          // Clear live indicator — we're about to reload with real data
          clearLiveIndicator();
          // If the message is NOT for the current session, mark sidebar
          if (sid !== _currentSessionId) {
            markSessionUnread(sid);
          }
          // Always refresh sidebar (sorts, updates metadata)
          refreshSidebar().then(function() {
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

// ─── Live streaming indicators ─────────────────────────────────────
var _liveIndicator = null;

function showLiveIndicator(phase) {
  var msgArea = document.getElementById('messages');
  if (!msgArea) return;

  if (!_liveIndicator) {
    _liveIndicator = document.createElement('div');
    _liveIndicator.className = 'msg assistant live-indicator';
    _liveIndicator.innerHTML = '<div class="msg-label">Kairos</div><div class="live-status"></div>';
    msgArea.appendChild(_liveIndicator);
  }

  var statusEl = _liveIndicator.querySelector('.live-status');
  if (!statusEl) return;

  if (phase === 'reasoning') {
    statusEl.textContent = '🤔 Pensando...';
  } else if (phase === 'content') {
    statusEl.textContent = '✍️ Escribiendo...';
  }
}

function addLiveTool(toolData) {
  var msgArea = document.getElementById('messages');
  if (!msgArea) return;

  // Ensure indicator exists
  if (!_liveIndicator) {
    showLiveIndicator('reasoning');
  }

  var statusEl = _liveIndicator.querySelector('.live-status');
  if (!statusEl) return;

  var icon = toolData.status === 'ok' ? '✓' : '✗';
  var pill = document.createElement('span');
  pill.className = 'tc-item ' + (toolData.status || 'calling');
  pill.innerHTML = icon + ' ' + (toolData.tool_name || 'tool');
  // Update status text and append pill
  statusEl.textContent = '🔧 Usando herramientas...';
  statusEl.appendChild(document.createTextNode(' '));
  statusEl.appendChild(pill);
}

function clearLiveIndicator() {
  if (_liveIndicator && _liveIndicator.parentNode) {
    _liveIndicator.parentNode.removeChild(_liveIndicator);
  }
  _liveIndicator = null;
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
