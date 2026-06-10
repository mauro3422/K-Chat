(function() {
  if (typeof KairosStream === 'undefined') return;

  KairosStream.on('tool_call', function(dataStr, state) {
    var info = JSON.parse(dataStr);
    if (info.status === 'partial') return;
    var allTc = state.asstDiv.querySelectorAll('.tool-calls');
    var tcEl = null;
    if (info.status === 'calling') {
      var foundIn = null;
      for (var ti = 0; ti < allTc.length; ti++) {
        if (allTc[ti].querySelector('[data-id="' + info.id + '"]')) { foundIn = allTc[ti]; break; }
      }
      if (foundIn) {
        tcEl = foundIn;
      } else if (allTc.length < state.reasoningEls.length) {
        tcEl = document.createElement('div');
        tcEl.className = 'tool-calls';
        var activePhaseIdx = state.reasoningEls.length - 1;
        var currentBody = state.bodyDivs[activePhaseIdx];
        if (currentBody) {
          currentBody.insertAdjacentElement('afterend', tcEl);
        } else if (activePhaseIdx >= 0 && state.reasoningEls[activePhaseIdx]) {
          state.reasoningEls[activePhaseIdx].insertAdjacentElement('afterend', tcEl);
        } else {
          state.asstDiv.appendChild(tcEl);
        }
        logUI('tool_calls_seq', state.reasoningEls.length);
      } else if (allTc.length > 0) {
        tcEl = allTc[allTc.length - 1];
      } else {
        tcEl = document.createElement('div');
        tcEl.className = 'tool-calls';
        var currentBody2 = state.bodyDivs[0];
        if (currentBody2) {
          currentBody2.insertAdjacentElement('afterend', tcEl);
        } else {
          state.asstDiv.appendChild(tcEl);
        }
        logUI('tool_calls_seq', 0);
      }
    } else {
      for (var ti2 = 0; ti2 < allTc.length; ti2++) {
        if (allTc[ti2].querySelector('[data-id="' + info.id + '"]')) { tcEl = allTc[ti2]; break; }
      }
      if (!tcEl && allTc.length > 0) tcEl = allTc[allTc.length - 1];
    }
    if (!tcEl) return;
    var existing = tcEl.querySelector('[data-id="' + info.id + '"]');
    if (info.status === 'calling') {
      if (!existing) {
        var span = document.createElement('span');
        span.className = 'tc-item calling';
        span.setAttribute('data-id', info.id);
        span.setAttribute('data-tool', info.name);
        span.innerHTML = '<span class="tc-spinner"></span> ' + KairosUtils.escHtml(info.name);
        tcEl.appendChild(span);
        logUI('tool_calling', info.name);
      }
    } else {
      if (existing) {
        existing.className = 'tc-item ' + info.status;
        existing.innerHTML = (info.status === 'ok' ? '&#10003; ' : '&#10007; ') + KairosUtils.escHtml(info.name);
        logUI('tool_' + info.status, info.name);
      } else {
        var span2 = document.createElement('span');
        span2.className = 'tc-item ' + info.status;
        span2.setAttribute('data-id', info.id);
        span2.innerHTML = (info.status === 'ok' ? '&#10003; ' : '&#10007; ') + KairosUtils.escHtml(info.name || '?');
        tcEl.appendChild(span2);
        logUI('tool_' + info.status, info.name);
      }
    }
  });
})();
