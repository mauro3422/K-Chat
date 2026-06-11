export function registerToolCallRenderer() {
  if (typeof KairosStream === 'undefined') return;

  KairosStream.on('tool_call', function(dataStr, state) {
    try {
      var info = JSON.parse(dataStr);
      if (info.status === 'partial') return;
      state.reasoningState.exit();
      state._toolTurnSinceLastContent = true;
      var allTc = state.asstDiv.querySelectorAll('.tool-calls');
      var tcEl = null;
      var foundIn = null;
      for (var ti = 0; ti < allTc.length; ti++) {
        if (allTc[ti].querySelector('[data-id="' + info.id + '"]')) { foundIn = allTc[ti]; break; }
      }
      if (foundIn) {
        tcEl = foundIn;
      } else if (info.status === 'calling') {
        tcEl = document.createElement('div');
        tcEl.className = 'tool-calls';
        state.asstDiv.appendChild(tcEl);
        logUI('tool_calls_seq', state.reasoningEls.length);
      } else {
        if (allTc.length > 0) tcEl = allTc[allTc.length - 1];
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
    } catch (e) {
      console.error('Tool call renderer error:', e);
    }
  });
}

registerToolCallRenderer();
