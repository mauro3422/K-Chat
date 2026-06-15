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

      // ── Live streaming: reasoning tokens ─────────────────────────
      if (event.type === 'stream:reasoning' && sid === _currentSessionId) {
        streamReasoning(event.data);
        return;
      }

      // ── Live streaming: content tokens ───────────────────────────
      if (event.type === 'stream:content' && sid === _currentSessionId) {
        streamContent(event.data);
        return;
      }

      // ── Live streaming: tool call ────────────────────────────────
      if (event.type === 'stream:tool' && sid === _currentSessionId) {
        streamTool(event.data);
        return;
      }

      // ── Live streaming: error ────────────────────────────────────
      if (event.type === 'stream:error' && sid === _currentSessionId) {
        streamError(event.data);
        return;
      }

      // ── Full message reload ──────────────────────────────────────
      if (event.type === 'new_message') {
        if (sid) {
          // Clear live message — we're about to reload with real data
          clearLiveMessage();
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
      if (typeof modules[0].MarkdownRenderer?.renderAll === 'function') modules[0].MarkdownRenderer.renderAll();
      if (typeof modules[1].scrollToBottom === 'function') modules[1].scrollToBottom();
    })
    .catch(function(err) {
      console.error('SSE reloadMessages failed:', err);
    });
}

// ─── Live streaming: build message token by token ─────────────────
var _liveMsg = null;       // the live message DOM element
var _liveReasoningEl = null;  // reasoning text element inside live msg
var _liveContentEl = null;    // content text element inside live msg
var _liveToolsEl = null;      // tool container inside live msg

function _ensureLiveMsg() {
  if (_liveMsg) return;
  var msgArea = document.getElementById('messages');
  if (!msgArea) return;

  _liveMsg = document.createElement('div');
  _liveMsg.className = 'msg assistant live-msg';

  // Label
  var label = document.createElement('div');
  label.className = 'msg-label';
  label.textContent = 'Kairos';
  _liveMsg.appendChild(label);

  // Reasoning (collapsible)
  var details = document.createElement('details');
  details.className = 'reasoning';
  details.open = true;
  var summary = document.createElement('summary');
  summary.textContent = 'Razonamiento';
  details.appendChild(summary);
  _liveReasoningEl = document.createElement('div');
  _liveReasoningEl.className = 'rt';
  details.appendChild(_liveReasoningEl);
  _liveMsg.appendChild(details);

  // Content area
  _liveContentEl = document.createElement('div');
  _liveContentEl.className = 'msg-body';
  _liveMsg.appendChild(_liveContentEl);

  // Tool calls area
  _liveToolsEl = document.createElement('div');
  _liveToolsEl.className = 'tool-calls';
  _liveMsg.appendChild(_liveToolsEl);

  msgArea.appendChild(_liveMsg);
  // Scroll to bottom to show live content
  import('./stream-lifecycle.js').then(function(sl) {
    if (typeof sl.scrollToBottom === 'function') sl.scrollToBottom();
  }).catch(function() {});
}

function streamReasoning(data) {
  _ensureLiveMsg();
  if (!_liveReasoningEl) return;
  // Replace text with the full accumulated reasoning (server sends accumulated text)
  _liveReasoningEl.textContent = data.text || '';
}

function streamContent(data) {
  _ensureLiveMsg();
  if (!_liveContentEl) return;
  // Replace text with the full accumulated content
  _liveContentEl.textContent = data.text || '';
  // Scroll to bottom as content streams
  import('./stream-lifecycle.js').then(function(sl) {
    if (typeof sl.scrollToBottom === 'function') sl.scrollToBottom();
  }).catch(function() {});
}

function streamTool(data) {
  _ensureLiveMsg();
  if (!_liveToolsEl) return;
  var icon = data.status === 'ok' ? '&#10003;' : '&#10007;';
  var pill = document.createElement('span');
  pill.className = 'tc-item ' + (data.status || 'calling');
  pill.innerHTML = icon + ' ' + (data.tool_name || 'tool');
  _liveToolsEl.appendChild(pill);
  // Scroll to show tool pill
  import('./stream-lifecycle.js').then(function(sl) {
    if (typeof sl.scrollToBottom === 'function') sl.scrollToBottom();
  }).catch(function() {});
}

function streamError(data) {
  _ensureLiveMsg();
  if (!_liveContentEl) return;
  _liveContentEl.textContent = '❌ Error: ' + (data.error || 'unknown');
  _liveContentEl.style.color = 'var(--accent-red, #ff4444)';
}

function clearLiveMessage() {
  if (_liveMsg && _liveMsg.parentNode) {
    _liveMsg.parentNode.removeChild(_liveMsg);
  }
  _liveMsg = null;
  _liveReasoningEl = null;
  _liveContentEl = null;
  _liveToolsEl = null;
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
