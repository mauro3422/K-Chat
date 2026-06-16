/**
 * Widget Templates — self-contained HTML widgets that work inside sandboxed iframes.
 * Each template function returns the full widget HTML/JS code.
 *
 * Each widget must be fully self-contained: HTML + CSS (inline <style>) + JS (inline <script>).
 */

/** Digital Clock widget — shows current time updating every second */
export function clockWidget(): string {
  return `<div class="w-root">
  <div class="w-clock">
    <div class="w-time" id="w-time">--:--:--</div>
    <div class="w-date" id="w-date"></div>
    <div class="w-label">Reloj en vivo</div>
  </div>
  <style>
    .w-root { padding: 8px; font-family: 'Courier New', monospace; text-align: center; }
    .w-clock { background: #1c2333; border-radius: 12px; padding: 20px; border: 1px solid #30363d; }
    .w-time { font-size: 2.8em; font-weight: bold; color: #58a6ff; letter-spacing: 3px; text-shadow: 0 0 20px rgba(88,166,255,0.3); }
    .w-date { font-size: 0.95em; color: #8b949e; margin-top: 6px; text-transform: capitalize; }
    .w-label { font-size: 0.75em; color: #484f58; margin-top: 10px; letter-spacing: 1px; text-transform: uppercase; }
  </style>
  <script>
    (function() {
      function pad(n) { return n < 10 ? '0' + n : '' + n; }
      function update() {
        var now = new Date();
        document.getElementById('w-time').textContent = pad(now.getHours()) + ':' + pad(now.getMinutes()) + ':' + pad(now.getSeconds());
        document.getElementById('w-date').textContent = now.toLocaleDateString('es-AR', { weekday:'long', year:'numeric', month:'long', day:'numeric' });
      }
      update();
      setInterval(update, 1000);
    })();
  </script>
</div>`;
}

/** Counter widget — simple +/- counter with reset */
export function counterWidget(): string {
  return `<div class="w-root">
  <div class="w-counter">
    <div class="w-counter-label">Contador Interactivo</div>
    <div class="w-counter-value" id="w-cv">0</div>
    <div class="w-counter-btns">
      <button class="w-btn" id="w-dec">−</button>
      <button class="w-btn w-btn-reset" id="w-reset">↺</button>
      <button class="w-btn w-btn-inc" id="w-inc">+</button>
    </div>
  </div>
  <style>
    .w-root { padding: 8px; font-family: system-ui, sans-serif; }
    .w-counter { background: #1c2333; border-radius: 12px; padding: 20px; border: 1px solid #30363d; text-align: center; }
    .w-counter-label { font-size: 0.8em; color: #8b949e; margin-bottom: 8px; }
    .w-counter-value { font-size: 3em; font-weight: 800; color: #f0883e; margin: 8px 0; }
    .w-counter-btns { display: flex; gap: 8px; justify-content: center; }
    .w-btn { width: 44px; height: 44px; border-radius: 10px; border: 1px solid #30363d; background: #0d1117; color: #c9d1d9; font-size: 1.3em; cursor: pointer; transition: all 0.15s; }
    .w-btn:hover { background: #21262d; border-color: #58a6ff; }
    .w-btn-inc { color: #3fb950; }
    .w-btn-reset { color: #8b949e; }
  </style>
  <script>
    (function() {
      var val = 0;
      var el = document.getElementById('w-cv');
      document.getElementById('w-inc').onclick = function() { val++; el.textContent = val; };
      document.getElementById('w-dec').onclick = function() { val--; el.textContent = val; };
      document.getElementById('w-reset').onclick = function() { val = 0; el.textContent = val; };
    })();
  </script>
</div>`;
}

/** Mini Dashboard — mock stats with CSS bars */
export function miniDashboardWidget(): string {
  return `<div class="w-root">
  <div class="w-dash">
    <div class="w-dash-title">📊 Dashboard Simulado</div>
    <div class="w-dash-row"><span class="w-dash-label">Requests</span><div class="w-dash-bar"><div class="w-dash-fill" style="width:78%"></div></div><span class="w-dash-num">1,234</span></div>
    <div class="w-dash-row"><span class="w-dash-label">Errores</span><div class="w-dash-bar"><div class="w-dash-fill w-dash-red" style="width:12%"></div></div><span class="w-dash-num">23</span></div>
    <div class="w-dash-row"><span class="w-dash-label">Latencia</span><div class="w-dash-bar"><div class="w-dash-fill w-dash-yellow" style="width:45%"></div></div><span class="w-dash-num">142ms</span></div>
    <div class="w-dash-row"><span class="w-dash-label">Uptime</span><div class="w-dash-bar"><div class="w-dash-fill w-dash-green" style="width:99%"></div></div><span class="w-dash-num">99.7%</span></div>
    <div class="w-dash-footer">Widget interactivo — los datos son estáticos de ejemplo</div>
  </div>
  <style>
    .w-root { padding: 8px; font-family: system-ui, sans-serif; }
    .w-dash { background: #1c2333; border-radius: 12px; padding: 16px; border: 1px solid #30363d; }
    .w-dash-title { font-size: 1em; font-weight: 600; color: #c9d1d9; margin-bottom: 12px; }
    .w-dash-row { display: flex; align-items: center; gap: 8px; margin: 6px 0; }
    .w-dash-label { width: 60px; font-size: 0.75em; color: #8b949e; flex-shrink: 0; }
    .w-dash-bar { flex: 1; height: 14px; background: #0d1117; border-radius: 7px; overflow: hidden; }
    .w-dash-fill { height: 100%; border-radius: 7px; background: #58a6ff; transition: width 0.5s; }
    .w-dash-red { background: #f85149; }
    .w-dash-yellow { background: #d29922; }
    .w-dash-green { background: #3fb950; }
    .w-dash-num { width: 50px; text-align: right; font-size: 0.8em; color: #c9d1d9; font-weight: 600; }
    .w-dash-footer { font-size: 0.65em; color: #484f58; margin-top: 12px; text-align: center; font-style: italic; }
  </style>
</div>`;
}

/** Weather Card — fake weather display */
export function weatherWidget(): string {
  return `<div class="w-root">
  <div class="w-weather">
    <div class="w-w-header">
      <span class="w-w-icon">☀️</span>
      <span class="w-w-temp" id="w-temp">24°</span>
    </div>
    <div class="w-w-city">Buenos Aires, AR</div>
    <div class="w-w-details">
      <span>💧 65%</span>
      <span>💨 12 km/h</span>
      <span>🌡️ 26° / 19°</span>
    </div>
    <div class="w-w-footer">Datos simulados — widget de ejemplo</div>
  </div>
  <style>
    .w-root { padding: 8px; font-family: system-ui, sans-serif; }
    .w-weather { background: linear-gradient(135deg, #1c2333 0%, #0d1117 100%); border-radius: 16px; padding: 20px; border: 1px solid #30363d; }
    .w-w-header { display: flex; align-items: center; gap: 12px; justify-content: center; }
    .w-w-icon { font-size: 3em; }
    .w-w-temp { font-size: 3em; font-weight: 300; color: #c9d1d9; }
    .w-w-city { text-align: center; font-size: 1em; color: #8b949e; margin: 4px 0 12px; }
    .w-w-details { display: flex; justify-content: center; gap: 16px; font-size: 0.8em; color: #8b949e; }
    .w-w-footer { font-size: 0.65em; color: #484f58; margin-top: 12px; text-align: center; font-style: italic; }
  </style>
</div>`;
}

/** Accordion widget — interactive collapsible sections */
export function accordionWidget(): string {
  return `<div class="w-root">
  <div class="w-acc">
    <div class="w-acc-title">📋 Acordeón Interactivo</div>
    <div class="w-acc-item">
      <div class="w-acc-header" data-idx="0">¿Qué es K-Chat? <span class="w-acc-arrow">▾</span></div>
      <div class="w-acc-body" id="w-ab-0">K-Chat es un asistente de IA con arquitectura de bloques Lego, construido en TypeScript y Python. Todo está desacoplado mediante inyección de dependencias y un bus de eventos.</div>
    </div>
    <div class="w-acc-item">
      <div class="w-acc-header" data-idx="1">¿Qué son los widgets? <span class="w-acc-arrow">▾</span></div>
      <div class="w-acc-body" id="w-ab-1">Los widgets son componentes HTML/JS autocontenidos que se ejecutan dentro de iframes sandboxed con <code>allow-scripts</code>. Son completamente seguros y aislados del DOM principal.</div>
    </div>
    <div class="w-acc-item">
      <div class="w-acc-header" data-idx="2">Arquitectura Lego <span class="w-acc-arrow">▾</span></div>
      <div class="w-acc-body" id="w-ab-2">Cada pieza del sistema es un bloque independiente que se conecta mediante interfaces bien definidas. Esto permite cambiar, probar y reemplazar componentes sin afectar al resto.</div>
    </div>
    <div class="w-acc-footer">Widget acordeón — hacé clic en cada sección</div>
  </div>
  <style>
    .w-root { padding: 8px; font-family: system-ui, sans-serif; }
    .w-acc { background: #1c2333; border-radius: 12px; padding: 12px; border: 1px solid #30363d; }
    .w-acc-title { font-size: 1em; font-weight: 600; color: #c9d1d9; margin-bottom: 10px; text-align: center; }
    .w-acc-item { border-bottom: 1px solid #21262d; }
    .w-acc-item:last-child { border-bottom: none; }
    .w-acc-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 8px; cursor: pointer; color: #c9d1d9; font-size: 0.9em; user-select: none; transition: background 0.15s; }
    .w-acc-header:hover { background: #21262d; border-radius: 4px; }
    .w-acc-arrow { color: #58a6ff; transition: transform 0.2s; font-size: 0.8em; }
    .w-acc-header.open .w-acc-arrow { transform: rotate(180deg); }
    .w-acc-body { padding: 0 8px 10px; color: #8b949e; font-size: 0.85em; line-height: 1.5; display: none; }
    .w-acc-body.open { display: block; }
    .w-acc-body code { background: #0d1117; padding: 1px 4px; border-radius: 3px; font-size: 0.9em; color: #f0883e; }
    .w-acc-footer { font-size: 0.65em; color: #484f58; margin-top: 8px; text-align: center; font-style: italic; }
  </style>
  <script>
    (function() {
      var headers = document.querySelectorAll('.w-acc-header');
      for (var i = 0; i < headers.length; i++) {
        headers[i].onclick = function() {
          var idx = this.dataset.idx;
          var body = document.getElementById('w-ab-' + idx);
          if (!body) return;
          body.classList.toggle('open');
          this.classList.toggle('open');
          // Notify parent iframe to resize after DOM change
          if (typeof sendHeight === 'function') setTimeout(sendHeight, 50);
        };
      }
    })();
  </script>
</div>`;
}

/** Notes widget — simple note-taking pad */
export function notesWidget(): string {
  return `<div class="w-root">
  <div class="w-notes">
    <div class="w-notes-title">📝 Bloc de Notas</div>
    <div class="w-notes-input-row">
      <input class="w-notes-input" id="w-ni" placeholder="Escribí una nota..." />
      <button class="w-notes-btn" id="w-nb">+</button>
    </div>
    <div class="w-notes-list" id="w-nl">
      <div class="w-notes-empty">Todavía no hay notas. ¡Agregá una!</div>
    </div>
    <div class="w-notes-footer">Widget interactivo — las notas se guardan en memoria</div>
  </div>
  <style>
    .w-root { padding: 8px; font-family: system-ui, sans-serif; }
    .w-notes { background: #1c2333; border-radius: 12px; padding: 12px; border: 1px solid #30363d; }
    .w-notes-title { font-size: 1em; font-weight: 600; color: #c9d1d9; margin-bottom: 10px; text-align: center; }
    .w-notes-input-row { display: flex; gap: 8px; margin-bottom: 10px; }
    .w-notes-input { flex: 1; padding: 8px 10px; border-radius: 8px; border: 1px solid #30363d; background: #0d1117; color: #c9d1d9; font-size: 0.85em; outline: none; }
    .w-notes-input:focus { border-color: #58a6ff; }
    .w-notes-btn { width: 36px; height: 36px; border-radius: 8px; border: 1px solid #30363d; background: #238636; color: #fff; font-size: 1.2em; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background 0.15s; }
    .w-notes-btn:hover { background: #2ea043; }
    .w-notes-list { min-height: 60px; }
    .w-notes-empty { text-align: center; color: #484f58; font-size: 0.8em; padding: 16px 0; }
    .w-note-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 8px; margin: 4px 0; border-radius: 6px; background: #0d1117; border: 1px solid #21262d; font-size: 0.85em; color: #c9d1d9; }
    .w-note-text { flex: 1; }
    .w-note-del { background: none; border: none; color: #f85149; cursor: pointer; font-size: 1em; padding: 0 4px; opacity: 0.6; }
    .w-note-del:hover { opacity: 1; }
    .w-notes-footer { font-size: 0.65em; color: #484f58; margin-top: 8px; text-align: center; font-style: italic; }
  </style>
  <script>
    (function() {
      var input = document.getElementById('w-ni');
      var btn = document.getElementById('w-nb');
      var list = document.getElementById('w-nl');
      var notes = [];
      function render() {
        if (notes.length === 0) {
          list.innerHTML = '<div class="w-notes-empty">Todavía no hay notas. ¡Agregá una!</div>';
          return;
        }
        list.innerHTML = '';
        for (var i = 0; i < notes.length; i++) {
          var item = document.createElement('div');
          item.className = 'w-note-item';
          item.innerHTML = '<span class="w-note-text">' + notes[i] + '</span><button class="w-note-del" data-idx="' + i + '">✕</button>';
          item.querySelector('.w-note-del').onclick = function() {
            notes.splice(parseInt(this.dataset.idx), 1);
            render();
            if (typeof sendHeight === 'function') setTimeout(sendHeight, 50);
          };
          list.appendChild(item);
        }
      }
      btn.onclick = function() {
        var text = input.value.trim();
        if (!text) return;
        notes.push(text);
        input.value = '';
        render();
        if (typeof sendHeight === 'function') setTimeout(sendHeight, 50);
      };
      input.onkeydown = function(e) {
        if (e.key === 'Enter') { btn.onclick(); }
      };
    })();
  </script>
</div>`;
}

/** All available widget types with their display names */
const ALL_WIDGETS: { name: string; fn: () => string }[] = [
  { name: 'clock', fn: clockWidget },
  { name: 'counter', fn: counterWidget },
  { name: 'dashboard', fn: miniDashboardWidget },
  { name: 'weather', fn: weatherWidget },
  { name: 'accordion', fn: accordionWidget },
  { name: 'notes', fn: notesWidget },
];

/** Generate widget blocks — all 6 for full test, or 1-3 random */
export function allWidgetsBlock(all?: boolean): string {
  const picked: typeof ALL_WIDGETS = [];

  if (all) {
    ALL_WIDGETS.forEach(w => picked.push(w));
  } else {
    const count = 1 + Math.floor(Math.random() * 3);
    const shuffled = [...ALL_WIDGETS].sort(() => Math.random() - 0.5);
    for (let i = 0; i < count; i++) {
      picked.push(shuffled[i]);
    }
  }

  return picked.map(w => `\`\`\`html-widget ${w.name}\n${w.fn()}\n\`\`\``).join('\n\n');
}

/** Pick a random widget template from all 6 types */
export function randomWidget(): string {
  const w = ALL_WIDGETS[Math.floor(Math.random() * ALL_WIDGETS.length)];
  return w.fn();
}
