import { SessionContext } from './session-context.js';
import { KairosUtils } from './utils.js';
import { KairosWidgets } from './widgets/index.js';
import { logUI, logStream, setDebugVisible, getStreamEvents, getUIEvents } from './log-ui.js';
import { ApiClient } from './api-client.js';
import {
  ASR_EVENT_TELEMETRY,
  ASR_EVENT_TEXT,
  getAsrTelemetryBuffer,
  getAsrVisibleText,
  getAsrTransportConfig,
  hasAsrTelemetry,
} from './asr/contract.js';

let debugVisible = false;
let debugControlsBound = false;

function timeToMs(t) {
  if (!t) return null;
  var p = t.split(':');
  if (p.length !== 3) return null;
  return (parseInt(p[0], 10) * 3600 + parseInt(p[1], 10) * 60 + parseFloat(p[2])) * 1000;
}

function escHtml(s) { return KairosUtils.escHtml(s); }

function getAsrTransportStatus() {
  var telemetry = getAsrTelemetryBuffer();
  var live = telemetry && telemetry.length > 0
    ? telemetry[telemetry.length - 1]
    : null;
  var mode = 'WebSocket';
  var config = getAsrTransportConfig().transport || 'websocket';
  var last = live && live.transport ? live.transport : 'ninguno';
  var state = live && live.success === false ? 'último fallo' : 'último ok';
  return mode + ' | config=' + config + ' | último=' + last + ' | ' + state;
}

function copyToClipboard(text, el) {
  navigator.clipboard.writeText(text).then(function() {
    el.textContent = 'copiado';
    setTimeout(function() { el.textContent = 'copy'; }, 1500);
  }).catch(function() {
    el.textContent = 'error';
  });
}

function renderUILog() {
  var el = document.getElementById('ui-log');
  if (!el) return;
  var events = getUIEvents();
  el.innerHTML = events.map(function(e) {
    return '<div class="sl-item"><span class="sl-idx">#' + e.id + '</span><span class="sl-ts">' + e.at + '</span><span class="sl-tag">' + e.label + '</span><span class="sl-data">' + escHtml(e.detail) + '</span></div>';
  }).join('');
}

function renderStreamLog() {
  var el = document.getElementById('stream-log');
  if (!el) return;
  var events = getStreamEvents();
  el.innerHTML = events.map(function(e) {
    return '<div class="sl-item sl-' + e.t.replace('_','-') + '"><span class="sl-ts">' + e.at + '</span><span class="sl-tag">' + e.t + '</span><span class="sl-data">' + escHtml((e.d || '').substring(0, 500)) + '</span></div>';
  }).join('');
}

function refreshWidgetInfo() {
  var el = document.getElementById('widget-log');
  if (!el || !KairosWidgets.debug) return;
  var widgetDebug = KairosWidgets.debug;
  if (Object.keys(widgetDebug).length === 0) {
    el.innerHTML = '<div class="sl-item">(sin widgets aun)</div>';
    return;
  }
  var lines = [];
  for (var wid in widgetDebug) {
    var w = widgetDebug[wid];
    lines.push('--- ' + wid + ' ---');
    var container = document.querySelector('[data-widget-id="' + wid + '"]');
    var iframe = container ? container.querySelector('iframe') : null;
    lines.push('iframe=' + (iframe ? iframe.offsetHeight + 'px' : '-'));
    (w.events || []).forEach(function(e) {
      lines.push(new Date(e.t).toISOString().slice(11,23) + ' ' + e.label + ' ' + e.detail);
    });
  }
  el.innerHTML = '<pre class="db-pre">' + escHtml(lines.join('\n')) + '</pre>';
}

function refreshBackendLogs() {
  var el = document.getElementById('backend-log');
  if (!el) return;
  ApiClient.loadBackendLogs().then(function(r) { return r.json(); }).then(function(data) {
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

function copyStreamLog(el) {
  var txt = getStreamEvents().map(function(e){ return e.id + ' ' + e.at + ' ' + e.t + ' ' + e.d; }).join('\n');
  copyToClipboard(txt, el);
}

function copyUILog(el) {
  var txt = getUIEvents().map(function(e){ return e.id + ' ' + e.at + ' ' + e.label + ' ' + e.detail; }).join('\n');
  copyToClipboard(txt, el);
}

function copyText(el) {
  var pre = el.parentElement.querySelector('pre');
  if (!pre) { el.textContent = '[]'; return; }
  copyToClipboard(pre.textContent, el);
}

function copyWidgetLog(el) {
  if (!KairosWidgets.debug || Object.keys(KairosWidgets.debug).length === 0) { el.textContent = '[]'; return; }
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

function copyBackendLogs(el) {
  ApiClient.loadBackendLogs().then(function(r) { return r.json(); }).then(function(data) {
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
  var allUI = getUIEvents();
  var starts = {};
  allUI.forEach(function(e) {
    if (e.label === 'stream_start' && e.detail.indexOf('mensaje=') >= 0) {
      starts[e.id] = { at: e.at, msg: e.detail.substring(0, 60) };
    }
  });
  parts.push('=== STREAM DURATIONS ===');
  var hasDuration = false;
  allUI.forEach(function(e) {
    if (e.label === 'stream_complete') {
      for (var sid in starts) {
        var s = starts[sid];
        var startMs = timeToMs(s.at);
        var endMs = timeToMs(e.at);
        if (startMs && endMs && endMs > startMs) {
          var dur = (endMs - startMs) / 1000;
          parts.push(s.at + ' → ' + e.at + ' = ' + dur.toFixed(1) + 's "' + s.msg + '"');
          hasDuration = true;
          delete starts[sid];
          break;
        }
      }
    }
  });
  if (!hasDuration) parts.push('(ninguno)');
  parts.push('');
  parts.push('=== UI EVENTS ===');
  parts.push(allUI.map(function(e){ return e.id + ' ' + e.at + ' ' + e.label + ' ' + e.detail; }).join('\n') || '(ninguno)');
  parts.push('');
  var allStream = getStreamEvents();
  parts.push('=== STREAM EVENTS ===');
  parts.push(allStream.map(function(e){ return e.id + ' ' + e.at + ' ' + e.t + ' ' + e.d; }).join('\n') || '(ninguno)');
  parts.push('');
  if (hasAsrTelemetry()) {
    parts.push('=== ASR (window) ===');
    parts.push(JSON.stringify(getAsrTelemetryBuffer(), null, 2));
    parts.push('');
  }
  parts.push('=== ASR TEXT ===');
  parts.push(getAsrVisibleText());
  parts.push('');
  if (KairosWidgets.debug && Object.keys(KairosWidgets.debug).length > 0) {
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
  ApiClient.loadDebugInfo(SessionContext.getSessionId()).then(function(r) { return r.json(); }).then(function(d) {
    parts.push('');
    parts.push('=== HISTORY ===');
    parts.push(JSON.stringify(d.history_before || [], null, 2));
    if (d.asr_telemetry && d.asr_telemetry.length > 0) {
      parts.push('');
      parts.push('=== ASR ===');
      parts.push(JSON.stringify(d.asr_telemetry, null, 2));
    }
    tryCopy();
  }).catch(function() { tryCopy(); });
  ApiClient.loadBackendLogs().then(function(r) { return r.json(); }).then(function(data2) {
    var logs = data2.logs || [];
    parts.push('');
    parts.push('=== BACKEND LOGS ===');
    parts.push(logs.map(function(log) {
      return new Date(log.ts * 1000).toISOString().slice(11, 23) + ' ' + log.level + ' ' + log.message;
    }).join('\n') || '(ninguno)');
    tryCopy();
  }).catch(function() { tryCopy(); });
}

function refreshDebug() {
  var dc = document.getElementById('debug-content');
  if (!dc) return;
  dc.textContent = 'Cargando...';
  ApiClient.loadDebugInfo(SessionContext.getSessionId()).then(function(r) { return r.json(); }).then(function(d) {
    var h = '';
    h += '<div class="db-section"><strong>Modelo:</strong> ' + (d.model || '-') + ' <button type="button" class="db-copy" data-copy-action="all" style="margin-left:8px">copy ALL</button></div>';
    h += '<div class="db-section"><strong>Razonamiento:</strong><button type="button" class="db-copy" data-copy-action="text">copy</button><pre class="db-pre">' + escHtml(d.reasoning || '(ninguno)') + '</pre></div>';
    h += '<div class="db-section"><strong>Tools:</strong><button type="button" class="db-copy" data-copy-action="text">copy</button><pre class="db-pre">' + escHtml(JSON.stringify(d.tool_calls || [], null, 2)) + '</pre></div>';
    h += '<div class="db-section"><strong>System Prompt:</strong><button type="button" class="db-copy" data-copy-action="text">copy</button><pre class="db-pre">' + escHtml((d.system_prompt || '').substring(0, 2000)) + '</pre></div>';
    h += '<details class="db-section"><summary>History (' + ((d.history_before||[]).length) + ')</summary><button type="button" class="db-copy" data-copy-action="text">copy</button><pre class="db-pre">' + escHtml(JSON.stringify(d.history_before || [], null, 2)) + '</pre></details>';
    h += '<div class="db-section"><strong>ASR Transport:</strong> ' + escHtml(getAsrTransportStatus()) + '</div>';
    h += '<div class="db-section"><strong>ASR Text:</strong><button type="button" class="db-copy" data-copy-action="text">copy</button><pre class="db-pre">' + escHtml(getAsrVisibleText()) + '</pre></div>';
    h += '<details class="db-section" open><summary>ASR Live (' + (getAsrTelemetryBuffer().length) + ')</summary><button type="button" class="db-copy" data-copy-action="text">copy</button><pre class="db-pre">' + escHtml(JSON.stringify(getAsrTelemetryBuffer(), null, 2)) + '</pre></details>';
    h += '<details class="db-section"><summary>ASR (' + ((d.asr_telemetry||[]).length) + ')</summary><button type="button" class="db-copy" data-copy-action="text">copy</button><pre class="db-pre">' + escHtml(JSON.stringify(d.asr_telemetry || [], null, 2)) + '</pre></details>';
    h += '<details class="db-section" open><summary>Stream</summary><button type="button" class="db-copy" data-copy-action="stream">copy</button><div id="stream-log" class="sl-container"></div></details>';
    h += '<details class="db-section"><summary>UI</summary><button type="button" class="db-copy" data-copy-action="ui">copy</button><div id="ui-log" class="sl-container"></div></details>';
    h += '<details class="db-section" open><summary>Widgets</summary><button type="button" class="db-copy" data-copy-action="widgets">copy</button><div id="widget-log" class="sl-container"></div></details>';
    h += '<details class="db-section"><summary>Backend Logs</summary><button type="button" class="db-copy" data-copy-action="backend">copy</button><div id="backend-log" class="sl-container">Cargando...</div></details>';
    dc.innerHTML = h;
    renderStreamLog();
    renderUILog();
    refreshWidgetInfo();
    refreshBackendLogs();
  }).catch(function(e) { if(dc) dc.textContent = 'Error: ' + e; });
}

function toggleDebug() {
  debugVisible = !debugVisible;
  setDebugVisible(debugVisible);
  var p = document.getElementById('debug-panel');
  var m = document.getElementById('main');
  if (p) p.classList.toggle('open', debugVisible);
  if (m) m.classList.toggle('shifted', debugVisible);
  if (debugVisible) refreshDebug();
}

function bindDebugControls() {
  if (debugControlsBound) return;
  debugControlsBound = true;
  window.addEventListener(ASR_EVENT_TELEMETRY, function() {
    if (debugVisible) refreshDebug();
  });
  window.addEventListener(ASR_EVENT_TEXT, function() {
    if (debugVisible) refreshDebug();
  });
  document.addEventListener('click', function(event) {
    var copyTarget = event.target && event.target.closest ? event.target.closest('.db-copy') : null;
    if (copyTarget) {
      var action = copyTarget.getAttribute('data-copy-action');
      if (action === 'all') copyAllDebug(copyTarget);
      else if (action === 'text') copyText(copyTarget);
      else if (action === 'stream') copyStreamLog(copyTarget);
      else if (action === 'ui') copyUILog(copyTarget);
      else if (action === 'widgets') copyWidgetLog(copyTarget);
      else if (action === 'backend') copyBackendLogs(copyTarget);
      return;
    }
    var target = event.target && event.target.closest ? event.target.closest('.debug-toggle, .debug-close') : null;
    if (!target) return;
    event.preventDefault();
    toggleDebug();
  });
}

export const KairosDebugPanel = {
  logUI,
  logStream,
  toggleDebug,
  refreshDebug,
  renderUILog,
  renderStreamLog,
  copyText,
  copyUILog,
  copyStreamLog,
  copyWidgetLog,
  copyBackendLogs,
  copyAllDebug,
  bindDebugControls,
  get debugVisible() { return debugVisible; }
};

export { refreshDebug };
