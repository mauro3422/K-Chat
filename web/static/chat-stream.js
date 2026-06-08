document.addEventListener('submit', function(e) {
  var form = e.target;
  if (form.id !== 'chat-form') return;
  e.preventDefault();

  var input = document.getElementById('msg-input');
  if (!input) input = form.querySelector('input[name="message"]');
  if (!input) return;
  var text = input.value.trim();
  if (!text) return;

  var oldUrl = window.location.pathname;
  if (oldUrl === '/') { window.history.replaceState({sid:sessionId}, '', '/sessions/' + sessionId); }

  input.disabled = true;
  document.getElementById('spinner').textContent = '...';

  document.getElementById('messages').insertAdjacentHTML('beforeend',
    '<div class="msg user"><div class="msg-label">Tu</div><div class="msg-body">' + text.replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</div></div>');
  var asstDiv = document.createElement('div');
  asstDiv.className = 'msg assistant';
  asstDiv.innerHTML = '<div class="msg-label">Kairos</div><div class="msg-body md-content">Pensando...</div>';
  document.getElementById('messages').appendChild(asstDiv);
  esc();

  (async function() {
      var reasoningText = '';
      var contentText = '';
      var buf = '';
      var firstToken = true;

      try {
        var resp = await fetch('/chat/' + sessionId + '?model=' + encodeURIComponent(defaultModel), {
          method: 'POST',
          headers: {'Content-Type': 'application/x-www-form-urlencoded'},
          body: 'message=' + encodeURIComponent(text)
        });
        var reader = resp.body.getReader();
        var decoder = new TextDecoder();
        var bodyDiv = asstDiv.querySelector('.msg-body');
        var reasoningEls = [];

        while (true) {
          var r = await reader.read();
          if (r.done) break;
          buf += decoder.decode(r.value);
          var lines = buf.split('\n');
          buf = lines.pop();
          for (var line of lines) {
            if (!line.trim()) continue;
            try { var msg = JSON.parse(line); } catch(e) { continue; }
            logStream(msg.t, msg.d);
            if (firstToken) { bodyDiv.textContent = ''; firstToken = false; logUI('pensando_cleared', ''+msg.t); }
            if (msg.t === 'reasoning') {
              reasoningText += msg.d;
              var toolCount = asstDiv.querySelectorAll('.tool-calls').length;
              if (reasoningEls.length <= toolCount) {
                if (reasoningEls.length > 0) {
                  var prev = reasoningEls[reasoningEls.length-1];
                  prev.querySelector('summary').textContent = 'Razonamiento';
                  prev.open = false;
                }
                var newDet = document.createElement('details');
                newDet.className = 'reasoning';
                newDet.open = true;
                newDet.innerHTML = '<summary>Razonando...</summary><div class="rt"></div>';
                if (toolCount > 0) {
                  var lastTc = asstDiv.querySelectorAll('.tool-calls');
                  lastTc[lastTc.length-1].insertAdjacentElement('afterend', newDet);
                } else {
                  bodyDiv.insertAdjacentElement('beforebegin', newDet);
                }
                reasoningEls.push(newDet);
                logUI('reasoning_phase', reasoningEls.length);
              }
              var rt = reasoningEls[reasoningEls.length-1].querySelector('.rt');
              if (rt) rt.textContent += msg.d;
            } else if (msg.t === 'content') {
              if (!contentText) logUI('body_start', msg.d.substring(0,60));
              contentText += msg.d;
              bodyDiv.textContent += msg.d;
            } else if (msg.t === 'tool_call') {
              var info = JSON.parse(msg.d);
              var allTc = asstDiv.querySelectorAll('.tool-calls');
              var tcEl = null;
              if (allTc.length < reasoningEls.length) {
                tcEl = document.createElement('div');
                tcEl.className = 'tool-calls';
                reasoningEls[reasoningEls.length-1].insertAdjacentElement('afterend', tcEl);
                logUI('tool_calls_seq', reasoningEls.length);
              } else {
                tcEl = allTc[allTc.length-1];
              }
              var existing = null;
              var items = tcEl.querySelectorAll('.tc-item');
              for (var i = 0; i < items.length; i++) {
                if (items[i].getAttribute('data-id') === info.id) { existing = items[i]; break; }
              }
              if (info.status === 'calling') {
                if (!existing) {
                  var span = document.createElement('span');
                  span.className = 'tc-item calling';
                  span.setAttribute('data-id', info.id);
                  span.setAttribute('data-tool', info.name);
                  span.innerHTML = '<span class="tc-spinner"></span> ' + escHtml(info.name);
                  tcEl.appendChild(span);
                  logUI('tool_calling', info.name);
                }
              } else {
                if (existing) {
                  existing.className = 'tc-item ' + info.status;
                  existing.innerHTML = (info.status === 'ok' ? '&#10003; ' : '&#10007; ') + info.name;
                  logUI('tool_'+info.status, info.name);
                }
              }
            }
          }
        }

        if (reasoningEls.length) {
          reasoningEls[reasoningEls.length-1].querySelector('summary').textContent = 'Razonamiento';
          logUI('reasoning_done', reasoningEls.length + ' fases');
        }

        // Render markdown en el contenido final
        if (contentText) {
          bodyDiv.innerHTML = DOMPurify.sanitize(parseMarkdown(contentText));
        }

        refreshSidebar();
        if (typeof debugVisible !== 'undefined' && debugVisible) refreshDebug();
      } catch(e2) {
        asstDiv.querySelector('.msg-body').textContent = 'Error: ' + e2;
      }
    input.disabled = false;
    input.value = '';
    document.getElementById('spinner').textContent = '';
    input.focus();
    esc();
  })();
});

function parseMarkdown(text) {
  if (typeof marked === 'undefined') return text;
  // Preprocesar tablas que usan '+' en sus separadores (ej. |---+---+---|)
  var cleanText = text.replace(/^([ \t]*\|[ \t]*[:\-\+\| \t]+)$/gm, function(match) {
    return match.replace(/\+/g, '-');
  });
  // Preprocesar notas al pie (Footnotes)
  // Referencias: [^1]
  cleanText = cleanText.replace(/\[\^([^\]]+)\](?!\:)/g, '<sup><a href="#fn-$1" id="fnref-$1" class="fn-ref">$1</a></sup>');
  // Definiciones: [^1]: texto
  cleanText = cleanText.replace(/^\[\^([^\]]+)\]:\s*(.*)$/gm, '<div class="footnote-def" id="fn-$1"><a href="#fnref-$1" class="fn-back">↩</a> <strong>$1:</strong> $2</div>');
  return marked.parse(cleanText);
}

function renderAllMarkdown() {
  if (typeof marked === 'undefined') return;
  document.querySelectorAll('.md-content').forEach(function(el) {
    if (el.dataset.rendered) return;
    var raw = el.textContent;
    if (raw.trim()) {
      el.innerHTML = DOMPurify.sanitize(parseMarkdown(raw));
    }
    el.dataset.rendered = '1';
  });
}

document.addEventListener('DOMContentLoaded', renderAllMarkdown);

// Render markdown when session messages are loaded via fetch
new MutationObserver(function() { renderAllMarkdown(); }).observe(
  document.getElementById('main') || document.body,
  { childList: true, subtree: true }
);
