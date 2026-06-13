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

function clearElement(el) {
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
}

function createLogItem(className, parts) {
  var row = document.createElement('div');
  row.className = className;
  parts.forEach(function(part) {
    var span = document.createElement('span');
    span.className = part.className;
    span.textContent = part.text;
    row.appendChild(span);
  });
  return row;
}

function createSingleLogItem(className, text) {
  var row = document.createElement('div');
  row.className = className;
  row.textContent = text;
  return row;
}

function createCopyButton(action, label, marginLeft) {
  var button = document.createElement('button');
  button.type = 'button';
  button.className = 'db-copy';
  button.setAttribute('data-copy-action', action);
  button.textContent = label;
  if (marginLeft) {
    button.style.marginLeft = marginLeft;
  }
  return button;
}

function createSection(title, copyAction, options) {
  var section = document.createElement(options && options.details ? 'details' : 'div');
  section.className = 'db-section';
  if (options && options.details && options.open) {
    section.open = true;
  }

  if (options && options.summaryText) {
    var summary = document.createElement('summary');
    summary.textContent = options.summaryText;
    section.appendChild(summary);
  }

  if (title) {
    var strong = document.createElement('strong');
    strong.textContent = title;
    section.appendChild(strong);
  }

  if (copyAction) {
    section.appendChild(createCopyButton(copyAction, options && options.copyLabel ? options.copyLabel : 'copy', options && options.copyMarginLeft));
  }

  if (options && options.preText !== undefined) {
    var pre = document.createElement('pre');
    pre.className = 'db-pre';
    pre.textContent = options.preText;
    section.appendChild(pre);
  }

  if (options && options.bodyNode) {
    section.appendChild(options.bodyNode);
  }

  return section;
}

function createDetailsSection(summaryText, copyAction, options) {
  return createSection(null, copyAction, {
    details: true,
    open: options && options.open,
    summaryText: summaryText,
    copyLabel: options && options.copyLabel,
    preText: options && options.preText,
    bodyNode: options && options.bodyNode,
  });
}

function renderUILog() {
  var el = document.getElementById('ui-log');
  if (!el) return;
  var events = getUIEvents();
  clearElement(el);
  events.forEach(function(e) {
    el.appendChild(createLogItem('sl-item', [
      { className: 'sl-idx', text: '#' + e.id },
      { className: 'sl-ts', text: e.at },
      { className: 'sl-tag', text: e.label },
      { className: 'sl-data', text: e.detail }
    ]));
  });
}

function renderStreamLog() {
  var el = document.getElementById('stream-log');
  if (!el) return;
  var events = getStreamEvents();
  clearElement(el);
  events.forEach(function(e) {
    el.appendChild(createLogItem('sl-item sl-' + e.t.replace('_','-'), [
      { className: 'sl-ts', text: e.at },
      { className: 'sl-tag', text: e.t },
      { className: 'sl-data', text: (e.d || '').substring(0, 500) }
    ]));
  });
}

function refreshWidgetInfo() {
  var el = document.getElementById('widget-log');
  if (!el || !KairosWidgets.debug) return;
  var widgetDebug = KairosWidgets.debug;
  if (Object.keys(widgetDebug).length === 0) {
    clearElement(el);
    el.appendChild(createSingleLogItem('sl-item', '(sin widgets aun)'));
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
  clearElement(el);
  var pre = document.createElement('pre');
  pre.className = 'db-pre';
  pre.textContent = lines.join('\n');
  el.appendChild(pre);
}

function refreshBackendLogs() {
  var el = document.getElementById('backend-log');
  if (!el) return;
  ApiClient.loadBackendLogs().then(function(r) { return r.json(); }).then(function(data) {
    var logs = data.logs || [];
    clearElement(el);
    logs.forEach(function(log) {
      var ts = new Date(log.ts * 1000).toISOString().slice(11, 23);
      var levelClass = 'sl-info';
      if (log.level === 'ERROR') levelClass = 'sl-error';
      else if (log.level === 'WARNING') levelClass = 'sl-warning';
      el.appendChild(createLogItem('sl-item ' + levelClass, [
        { className: 'sl-ts', text: ts },
        { className: 'sl-tag', text: log.level },
        { className: 'sl-data', text: log.message }
      ]));
    });
  }).catch(function(e) {
    clearElement(el);
    el.appendChild(createSingleLogItem('sl-item sl-error', 'Error cargando logs: ' + e.message));
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
    clearElement(dc);
    dc.appendChild(createSection('Modelo:', 'all', {
      copyLabel: 'copy ALL',
      copyMarginLeft: '8px',
      bodyNode: document.createTextNode(' ' + (d.model || '-'))
    }));
    dc.appendChild(createSection('Razonamiento:', 'text', {
      preText: d.reasoning || '(ninguno)'
    }));
    dc.appendChild(createSection('Tools:', 'text', {
      preText: JSON.stringify(d.tool_calls || [], null, 2)
    }));
    dc.appendChild(createSection('System Prompt:', 'text', {
      preText: (d.system_prompt || '').substring(0, 2000)
    }));
    dc.appendChild(createDetailsSection('History (' + ((d.history_before||[]).length) + ')', 'text', {
      preText: JSON.stringify(d.history_before || [], null, 2)
    }));
    dc.appendChild(createSection('ASR Transport:', null, {
      bodyNode: document.createTextNode(' ' + getAsrTransportStatus())
    }));
    dc.appendChild(createSection('ASR Text:', 'text', {
      preText: getAsrVisibleText()
    }));
    dc.appendChild(createDetailsSection('ASR Live (' + (getAsrTelemetryBuffer().length) + ')', 'text', {
      open: true,
      preText: JSON.stringify(getAsrTelemetryBuffer(), null, 2)
    }));
    dc.appendChild(createDetailsSection('ASR (' + ((d.asr_telemetry||[]).length) + ')', 'text', {
      preText: JSON.stringify(d.asr_telemetry || [], null, 2)
    }));
    dc.appendChild(createDetailsSection('Stream', 'stream', {
      open: true,
      bodyNode: (function() {
        var node = document.createElement('div');
        node.id = 'stream-log';
        node.className = 'sl-container';
        return node;
      })()
    }));
    dc.appendChild(createDetailsSection('UI', 'ui', {
      bodyNode: (function() {
        var node = document.createElement('div');
        node.id = 'ui-log';
        node.className = 'sl-container';
        return node;
      })()
    }));
    dc.appendChild(createDetailsSection('Widgets', 'widgets', {
      open: true,
      bodyNode: (function() {
        var node = document.createElement('div');
        node.id = 'widget-log';
        node.className = 'sl-container';
        return node;
      })()
    }));
    dc.appendChild(createDetailsSection('Backend Logs', 'backend', {
      bodyNode: (function() {
        var node = document.createElement('div');
        node.id = 'backend-log';
        node.className = 'sl-container';
        node.textContent = 'Cargando...';
        return node;
      })()
    }));
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
