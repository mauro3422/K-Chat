var debugVisible = false;
var streamEvents = [];
var streamEvId = 0;
var uiEvents = [];
var uiEvId = 0;

function logStream(tipo, data) {
  streamEvents.push({id: ++streamEvId, t: tipo, d: typeof data === 'string' ? data.substring(0, 120) : JSON.stringify(data).substring(0, 120), at: new Date().toISOString().slice(11,23)});
  if (streamEvents.length > 100) streamEvents.shift();
  if (debugVisible) renderStreamLog();
}

function logUI(label, detail) {
  uiEvents.push({id: ++uiEvId, label: label, detail: String(detail || '').substring(0, 160), at: new Date().toISOString().slice(11,23)});
  if (uiEvents.length > 60) uiEvents.shift();
  if (debugVisible) renderUILog();
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
    return '<div class="sl-item sl-' + e.t.replace('_','-') + '"><span class="sl-idx">#' + e.id + '</span><span class="sl-ts">' + e.at + '</span><span class="sl-tag">' + e.t + '</span><span class="sl-data">' + escHtml(e.d) + '</span></div>';
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
  navigator.clipboard.writeText(txt).then(function() {
    el.textContent = 'copiado';
    setTimeout(function(){ el.textContent = 'copy'; }, 1500);
  }).catch(function(){ el.textContent = 'error'; });
}

function copyUILog(el) {
  var txt = uiEvents.map(function(e){ return e.id + ' ' + e.at + ' ' + e.label + ' ' + e.detail; }).join('\n');
  navigator.clipboard.writeText(txt).then(function() {
    el.textContent = 'copiado';
    setTimeout(function(){ el.textContent = 'copy'; }, 1500);
  }).catch(function(){ el.textContent = 'error'; });
}

function copyText(el) {
  var pre = el.parentElement.querySelector('pre');
  if (!pre) { el.textContent = '[]'; return; }
  navigator.clipboard.writeText(pre.textContent).then(function() {
    el.textContent = 'copiado';
    setTimeout(function(){ el.textContent = 'copy'; }, 1500);
  }).catch(function(){ el.textContent = 'error'; });
}

function refreshDebug() {
  var dc = document.getElementById('debug-content');
  if (!dc) return;
  dc.textContent = 'Cargando...';
  fetch('/sessions/' + sessionId + '/debug').then(function(r) { return r.json(); }).then(function(d) {
    var h = '';
    h += '<div class="db-section"><strong>Modelo:</strong> ' + (d.model || '-') + '</div>';
    h += '<div class="db-section"><strong>Razonamiento:</strong><span class="db-copy" onclick="copyText(this)">copy</span><pre class="db-pre">' + escHtml(d.reasoning || '(ninguno)') + '</pre></div>';
    h += '<div class="db-section"><strong>Tools:</strong><span class="db-copy" onclick="copyText(this)">copy</span><pre class="db-pre">' + escHtml(JSON.stringify(d.tool_calls || [], null, 2)) + '</pre></div>';
    h += '<div class="db-section"><strong>System Prompt:</strong><span class="db-copy" onclick="copyText(this)">copy</span><pre class="db-pre">' + escHtml((d.system_prompt || '').substring(0, 2000)) + '</pre></div>';
    h += '<details class="db-section"><summary>History (' + ((d.history_before||[]).length) + ')</summary><span class="db-copy" onclick="copyText(this)">copy</span><pre class="db-pre">' + escHtml(JSON.stringify(d.history_before || [], null, 2)) + '</pre></details>';
    h += '<details class="db-section" open><summary>Stream</summary><span class="db-copy" onclick="copyStreamLog(this)">copy</span><div id="stream-log" class="sl-container"></div></details>';
    h += '<details class="db-section"><summary>UI</summary><span class="db-copy" onclick="copyUILog(this)">copy</span><div id="ui-log" class="sl-container"></div></details>';
    h += '<details class="db-section" open><summary>Widgets</summary><div id="widget-log" class="sl-container"></div></details>';
    dc.innerHTML = h;
    renderStreamLog();
    renderUILog();
    refreshWidgetInfo();
  }).catch(function(e) { if(dc) dc.textContent = 'Error: ' + e; });
}

function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function refreshWidgetInfo() {
  var el = document.getElementById('widget-log');
  if (!el || typeof widgetDebug === 'undefined') return;
  el.innerHTML = widgetSectionHtml ? '' : '';
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

var _origLogUI = logUI;
logUI = function(label, detail) {
  _origLogUI(label, detail);
  if (typeof widgetDebug !== 'undefined' && label.indexOf('[W]') === 0) {
    setTimeout(refreshWidgetInfo, 50);
  }
};
