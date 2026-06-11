import { SessionContext } from './modules/session-context.js';

let debugVisible = false;
const streamEvents = [];
let streamEvId = 0;
const uiEvents = [];
let uiEvId = 0;

function logStream(tipo, data) {
  streamEvents.push({id: ++streamEvId, t: tipo, d: typeof data === 'string' ? data.substring(0, 120) : JSON.stringify(data).substring(0, 120), at: new Date().toISOString().slice(11,23)});
  if (streamEvents.length > 100) streamEvents.shift();
  if (debugVisible) renderStreamLog();
}

function logUI(label, detail) {
  uiEvents.push({id: ++uiEvId, label: label, detail: String(detail || '').substring(0, 160), at: new Date().toISOString().slice(11,23)});
  if (uiEvents.length > 60) uiEvents.shift();
  if (debugVisible) renderUILog();
  if (typeof KairosWidgets !== 'undefined' && label.indexOf('[W]') === 0) {
    setTimeout(refreshWidgetInfo, 50);
  }
}

function renderUILog() {
  var el = document.getElementById('ui-log');
  if (!el) return;
  el.innerHTML = uiEvents.map(function(e) {
    return '<div class="sl-item"><span class="sl-idx">#' + e.id + '</span><span class="sl-ts">' + e.at + '</span><span class="sl-tag">' + e.label + '</span><span class="sl-data">' + escHtml(e.detail) + '</span></div>';
  }).join('');
}

function renderStreamLog() {
  var el = document.getElementById('stream-log');
  if (!el) return;
  el.innerHTML = streamEvents.map(function(e) {
    return '<div class="sl-item sl-' + e.t.replace('_','-') + '"><span class="sl-ts">' + e.at + '</span><span class="sl-tag">' + e.t + '</span><span class="sl-data">' + escHtml(e.d) + '</span></div>';
  }).join('');
}

function toggleDebug() {
  debugVisible = !debugVisible;
  var p = document.getElementById('debug-panel');
  var m = document.getElementById('main');
  if (p) p.classList.toggle('open', debugVisible);
  if (m) m.classList.toggle('shifted', debugVisible);
  if (debugVisible) refreshDebug();
}

function copyStreamLog(el) {
  var txt = streamEvents.map(function(e){ return e.id + ' ' + e.at + ' ' + e.t + ' ' + e.d; }).join('\n');
  copyToClipboard(txt, el);
}

function copyUILog(el) {
  var txt = uiEvents.map(function(e){ return e.id + ' ' + e.at + ' ' + e.label + ' ' + e.detail; }).join('\n');
  copyToClipboard(txt, el);
}

function copyText(el) {
  var pre = el.parentElement.querySelector('pre');
  if (!pre) { el.textContent = '[]'; return; }
  copyToClipboard(pre.textContent, el);
}

function copyWidgetLog(el) {
  if (typeof KairosWidgets === 'undefined') { el.textContent = '[]'; return; }
  var widgetDebug = KairosWidgets.debug;
  var lines = [];
  for (var wid in widgetDebug) {
    var w = widgetDebug[wid];
    lines.push('--- ' + wid + ' ---');
    var container = document.querySelector('[data-widget-id="' + wid + '"]');
    var iframe = container ? container.querySelector('iframe') : null;
    var curH = iframe ? iframe.offsetHeight + 'px' : '-';
    lines.push('iframe=' + curH);
    (w.events || []).forEach(function(e) {
      var ts = new Date(e.t).toISOString().slice(11,23);
      lines.push(ts + ' ' + e.label + ' ' + e.detail);
    });
  }
  copyToClipboard(lines.join('\n'), el);
}

function refreshDebug() {
  var dc = document.getElementById('debug-content');
  if (!dc) return;
  dc.textContent = 'Cargando...';
  var urlBuilder = SessionContext.createSessionUrlBuilder();
  fetch(urlBuilder.debug()).then(function(r) { return r.json(); }).then(function(d) {
    var h = '';
    h += '<div class="db-section"><strong>Modelo:</strong> ' + (d.model || '-') + ' <span class="db-copy" onclick="copyAllDebug(this)" style="margin-left:8px">copy ALL</span></div>';
    h += '<div class="db-section"><strong>Razonamiento:</strong><span class="db-copy" onclick="copyText(this)">copy</span><pre class="db-pre">' + escHtml(d.reasoning || '(ninguno)') + '</pre></div>';
    h += '<div class="db-section"><strong>Tools:</strong><span class="db-copy" onclick="copyText(this)">copy</span><pre class="db-pre">' + escHtml(JSON.stringify(d.tool_calls || [], null, 2)) + '</pre></div>';
    h += '<div class="db-section"><strong>System Prompt:</strong><span class="db-copy" onclick="copyText(this)">copy</span><pre class="db-pre">' + escHtml((d.system_prompt || '').substring(0, 2000)) + '</pre></div>';
    h += '<details class="db-section"><summary>History (' + ((d.history_before||[]).length) + ')</summary><span class="db-copy" onclick="copyText(this)">copy</span><pre class="db-pre">' + escHtml(JSON.stringify(d.history_before || [], null, 2)) + '</pre></details>';
    h += '<details class="db-section" open><summary>Stream</summary><span class="db-copy" onclick="copyStreamLog(this)">copy</span><div id="stream-log" class="sl-container"></div></details>';
    h += '<details class="db-section"><summary>UI</summary><span class="db-copy" onclick="copyUILog(this)">copy</span><div id="ui-log" class="sl-container"></div></details>';
    h += '<details class="db-section" open><summary>Widgets</summary><span class="db-copy" onclick="copyWidgetLog(this)">copy</span><div id="widget-log" class="sl-container"></div></details>';
    h += '<details class="db-section"><summary>Backend Logs</summary><span class="db-copy" onclick="copyBackendLogs(this)">copy</span><div id="backend-log" class="sl-container">Cargando...</div></details>';
    dc.innerHTML = h;
    renderStreamLog();
    renderUILog();
    refreshWidgetInfo();
    refreshBackendLogs();
  }).catch(function(e) { if(dc) dc.textContent = 'Error: ' + e; });
}

function refreshBackendLogs() {
  var el = document.getElementById('backend-log');
  if (!el) return;
  fetch('/debug/backend-logs').then(function(r) { return r.json(); }).then(function(data) {
    var logs = data.logs || [];
    el.innerHTML = logs.map(function(log) {
      var ts = new Date(log.ts * 1000).toISOString().slice(11, 23);
      var levelClass = 'sl-info';
      if (log.level === 'ERROR') levelClass = 'sl-error';
      else if (log.level === 'WARNING') levelClass = 'sl-warning';
      return '<div class="sl-item ' + levelClass + '"><span class="sl-ts">' + ts + '</span><span class="sl-tag">' + log.level + '</span><span class="sl-data">' + escHtml(log.message) + '</span></div>';
    }).join('');
  }).catch(function(e) {
    el.innerHTML = '<div class="sl-item sl-error">Error cargando logs: ' + escHtml(e.message) + '</div>';
  });
}

function copyBackendLogs(el) {
  fetch('/debug/backend-logs').then(function(r) { return r.json(); }).then(function(data) {
    var logs = data.logs || [];
    var txt = logs.map(function(log) {
      var ts = new Date(log.ts * 1000).toISOString().slice(11, 23);
      return ts + ' ' + log.level + ' ' + log.message;
    }).join('\n');
    copyToClipboard(txt, el);
  }).catch(function() { el.textContent = 'error'; });
}

function copyAllDebug(el) {
  var parts = [];
  parts.push('=== UI EVENTS ===');
  parts.push(uiEvents.map(function(e){ return e.id + ' ' + e.at + ' ' + e.label + ' ' + e.detail; }).join('\n') || '(ninguno)');
  parts.push('');
  parts.push('=== STREAM EVENTS ===');
  parts.push(streamEvents.map(function(e){ return e.id + ' ' + e.at + ' ' + e.t + ' ' + e.d; }).join('\n') || '(ninguno)');
  parts.push('');

  if (typeof KairosWidgets !== 'undefined') {
    var widgetDebug = KairosWidgets.debug;
    parts.push('=== WIDGETS ===');
    for (var wid in widgetDebug) {
      var w = widgetDebug[wid];
      parts.push('--- ' + wid + ' ---');
      var container = document.querySelector('[data-widget-id="' + wid + '"]');
      var iframe = container ? container.querySelector('iframe') : null;
      parts.push('iframe=' + (iframe ? iframe.offsetHeight + 'px' : '-'));
      (w.events || []).forEach(function(e) {
        parts.push(new Date(e.t).toISOString().slice(11,23) + ' ' + e.label + ' ' + e.detail);
      });
    }
  }

  var dc = document.getElementById('debug-content');
  el.textContent = 'Copiando...';

  var pending = 2;
  function tryCopy() {
    pending--;
    if (pending === 0) {
      copyToClipboard(parts.join('\n'), el);
    }
  }

  var urlBuilder = SessionContext.createSessionUrlBuilder();
  fetch(urlBuilder.debug()).then(function(r) { return r.json(); }).then(function(d) {
    parts.push('');
    parts.push('=== HISTORY ===');
    parts.push(JSON.stringify(d.history_before || [], null, 2));
    tryCopy();
  }).catch(function() { tryCopy(); });

  fetch('/debug/backend-logs').then(function(r) { return r.json(); }).then(function(data2) {
    var logs = data2.logs || [];
    parts.push('');
    parts.push('=== BACKEND LOGS ===');
    parts.push(logs.map(function(log) {
      return new Date(log.ts * 1000).toISOString().slice(11, 23) + ' ' + log.level + ' ' + log.message;
    }).join('\n') || '(ninguno)');
    tryCopy();
  }).catch(function() { tryCopy(); });
}

function copyToClipboard(text, el) {
  navigator.clipboard.writeText(text).then(function() {
    el.textContent = 'copiado';
    setTimeout(function() { el.textContent = 'copy'; }, 1500);
  }).catch(function() {
    el.textContent = 'error';
  });
}

function escHtml(s) { return KairosUtils.escHtml(s); }

function refreshWidgetInfo() {
  var el = document.getElementById('widget-log');
  if (!el || typeof KairosWidgets === 'undefined') return;
  var widgetDebug = KairosWidgets.debug;
  if (Object.keys(widgetDebug).length === 0) {
    el.innerHTML = '<div class="sl-item">(sin widgets aun)</div>';
    return;
  }
  var html = '';
  for (var wid in widgetDebug) {
    var w = widgetDebug[wid];
    var container = document.querySelector('[data-widget-id="' + wid + '"]');
    var iframe = container ? container.querySelector('iframe') : null;
    var curH = iframe ? iframe.offsetHeight + 'px' : '-';
    var containerH = container ? container.offsetHeight + 'px' : '-';
    var hasScroll = container && container.parentElement ? (container.parentElement.scrollHeight > container.parentElement.clientHeight ? 'SI' : 'no') : '?';
    html += '<div class="wi-block">';
    html += '<strong>' + escHtml(wid) + '</strong> iframe=' + curH + ' contenedor=' + containerH + ' scroll-padre=' + hasScroll;
    html += '<div class="sl-container" style="max-height:120px">';
    html += (w.events || []).map(function(e) {
      var ts = new Date(e.t).toISOString().slice(11,23);
      var cls = e.label.indexOf('ERROR') >= 0 ? 'sl-error' : '';
      return '<div class="sl-item ' + cls + '"><span class="sl-ts">' + ts + '</span><span class="sl-tag">' + escHtml(e.label) + '</span><span class="sl-data">' + escHtml(e.detail) + '</span></div>';
    }).join('');
    html += '</div></div>';
  }
  el.innerHTML = html;
}

export const KairosDebug = {
  logStream, logUI, toggleDebug,
  copyStreamLog, copyUILog, copyText, copyWidgetLog,
  refreshDebug, copyBackendLogs, copyAllDebug,
  get debugVisible() { return debugVisible; }
};

// Backwards-compatible window aliases for inline onclick handlers in dynamic HTML.
// These reference functions from the KairosDebug module but must remain global
// because onclick="toggleDebug()" / onclick="copyText(this)" etc. are injected
// as innerHTML strings (see refreshDebug).
window.logStream = KairosDebug.logStream;
window.logUI = KairosDebug.logUI;
window.toggleDebug = KairosDebug.toggleDebug;
window.refreshDebug = KairosDebug.refreshDebug;
window.copyStreamLog = KairosDebug.copyStreamLog;
window.copyUILog = KairosDebug.copyUILog;
window.copyText = KairosDebug.copyText;
window.copyWidgetLog = KairosDebug.copyWidgetLog;
window.copyBackendLogs = KairosDebug.copyBackendLogs;
window.copyAllDebug = KairosDebug.copyAllDebug;
