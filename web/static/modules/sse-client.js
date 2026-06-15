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

// ─── Live streaming: build message phase by phase ────────────────
var _liveMsg = null;
var _livePhase = null;          // 'reasoning' | 'tool' | 'content' | null
var _liveReasoningEls = [];     // .rt elements, one per reasoning phase
var _liveContentEls = [];       // .msg-body elements, one per content phase
var _liveCurrentTools = null;   // current .tool-calls container (null = no tool phase)

function _ensureLiveMsg() {
  if (_liveMsg) return;
  var msgArea = document.getElementById('messages');
  if (!msgArea) return;

  _liveMsg = document.createElement('div');
  _liveMsg.className = 'msg assistant live-msg';

  var label = document.createElement('div');
  label.className = 'msg-label';
  label.textContent = 'Kairos';
  _liveMsg.appendChild(label);

  msgArea.appendChild(_liveMsg);
  import('./stream-lifecycle.js').then(function(sl) {
    if (typeof sl.scrollToBottom === 'function') sl.scrollToBottom();
  }).catch(function() {});
}

function _closeReasoning() {
  if (_liveReasoningEls.length > 0) {
    var lastRt = _liveReasoningEls[_liveReasoningEls.length - 1];
    var details = lastRt && lastRt.parentNode;
    if (details) {
      var s = details.querySelector('summary');
      if (s) s.textContent = 'Razonamiento';
      details.open = false;
    }
  }
}

function streamReasoning(data) {
  _ensureLiveMsg();
  if (_livePhase !== 'reasoning') {
    // Transition INTO reasoning — close any previous tool container
    _liveCurrentTools = null;
    _closeReasoning();

    var details = document.createElement('details');
    details.className = 'reasoning';
    details.open = true;
    var summary = document.createElement('summary');
    summary.textContent = 'Razonando...';
    details.appendChild(summary);
    var rt = document.createElement('div');
    rt.className = 'rt';
    details.appendChild(rt);
    _liveMsg.appendChild(details);
    _liveReasoningEls.push(rt);
    _livePhase = 'reasoning';
  }
  // Update last reasoning element (server sends full accumulated text)
  var rt = _liveReasoningEls[_liveReasoningEls.length - 1];
  if (rt) rt.textContent = data.text || '';
}

function streamTool(data) {
  _ensureLiveMsg();
  if (_livePhase !== 'tool') {
    // Transition INTO tool phase — create a fresh tool-calls container
    _liveCurrentTools = document.createElement('div');
    _liveCurrentTools.className = 'tool-calls';
    _liveMsg.appendChild(_liveCurrentTools);
    _livePhase = 'tool';
    // Scroll to show tools
    import('./stream-lifecycle.js').then(function(sl) {
      if (typeof sl.scrollToBottom === 'function') sl.scrollToBottom();
    }).catch(function() {});
  }
  var icon = data.status === 'ok' ? '&#10003;' : '&#10007;';
  var pill = document.createElement('span');
  pill.className = 'tc-item ' + (data.status || 'calling');
  pill.innerHTML = icon + ' ' + (data.tool_name || 'tool');
  _liveCurrentTools.appendChild(pill);
}

function streamContent(data) {
  _ensureLiveMsg();
  if (_livePhase !== 'content') {
    // Transition INTO content — close tools, close reasoning
    _liveCurrentTools = null;
    _closeReasoning();

    var el = document.createElement('div');
    el.className = 'msg-body';
    _liveMsg.appendChild(el);
    _liveContentEls.push(el);
    _livePhase = 'content';
  }
  var el = _liveContentEls[_liveContentEls.length - 1];
  if (!el) return;
  var text = data.text || '';
  if (text && typeof marked !== 'undefined') {
    var html = marked.parse(text);
    if (typeof DOMPurify !== 'undefined') {
      html = DOMPurify.sanitize(html);
    }
    el.innerHTML = html;
  } else {
    el.textContent = text;
  }
  import('./stream-lifecycle.js').then(function(sl) {
    if (typeof sl.scrollToBottom === 'function') sl.scrollToBottom();
  }).catch(function() {});
}

function streamError(data) {
  _ensureLiveMsg();
  _liveCurrentTools = null;
  var el = _liveContentEls.length > 0 ? _liveContentEls[_liveContentEls.length - 1] : null;
  if (!el) {
    el = document.createElement('div');
    el.className = 'msg-body';
    _liveMsg.appendChild(el);
    _liveContentEls.push(el);
  }
  el.textContent = '❌ Error: ' + (data.error || 'unknown');
  el.style.color = 'var(--accent-red, #ff4444)';
}

function clearLiveMessage() {
  if (_liveMsg && _liveMsg.parentNode) {
    _liveMsg.parentNode.removeChild(_liveMsg);
  }
  _liveMsg = null;
  _livePhase = null;
  _liveReasoningEls = [];
  _liveContentEls = [];
  _liveCurrentTools = null;
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
