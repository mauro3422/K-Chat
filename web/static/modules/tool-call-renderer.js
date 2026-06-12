import { KairosUtils } from './utils.js';
import C from './dom-contracts.js';
import { KairosStream } from './stream-dispatcher.js';

export function registerToolCallRenderer() {
  KairosStream.on('tool_call', function(dataStr, ctx) {
    try {
      var state = ctx;
      if (ctx && typeof ctx.markToolTurn === 'function') {
        state = {
          asstDiv: ctx.getAsstDiv(),
          reasoningEls: ctx.getReasoningEls(),
          reasoningState: ctx.getReasoningState(),
          _toolTurnSinceLastContent: ctx.getToolTurnSinceLastContent(),
          context: ctx
        };
      }

      var info = JSON.parse(dataStr);
      if (info.status === 'partial') return;
      state.reasoningState.exit();
      state._toolTurnSinceLastContent = true;
      if (state.context) {
        state.context.markToolTurn();
      }
      var allTc = state.asstDiv.querySelectorAll('.' + C.TOOL_CALLS);
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
          tcEl.className = C.TOOL_CALLS;
          state.asstDiv.appendChild(tcEl);
          logUI('tool_calls_seq', allTc.length);
        } else if (allTc.length > 0) {
          tcEl = allTc[allTc.length - 1];
        } else {
          tcEl = document.createElement('div');
          tcEl.className = C.TOOL_CALLS;
          state.asstDiv.appendChild(tcEl);
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
          span.className = C.TC_ITEM_CALLING;
          span.setAttribute('data-id', info.id);
          span.setAttribute('data-tool', info.name);
          span.innerHTML = '<span class="tc-spinner"></span> ' + KairosUtils.escHtml(info.name);
          tcEl.appendChild(span);
          logUI('tool_calling', info.name);
        }
      } else {
        if (existing) {
          existing.className = C.TC_ITEM + ' ' + info.status;
          existing.innerHTML = (info.status === 'ok' ? '&#10003; ' : '&#10007; ') + KairosUtils.escHtml(info.name);
          logUI('tool_' + info.status, info.name);
        } else {
          var span2 = document.createElement('span');
          span2.className = C.TC_ITEM + ' ' + info.status;
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
