import C from './dom-contracts.js';
import { StreamDispatcher } from './stream-dispatcher.js';
import { logUI } from './log-ui.js';

function createToolPillClass(status) {
  return C.TC_ITEM + ' ' + status;
}

function createToolPillText(status, name) {
  return (status === 'ok' ? '✓ ' : '✗ ') + (name || '?');
}

function createCallingPill(name) {
  var span = document.createElement('span');
  span.className = C.TC_ITEM_CALLING;
  span.setAttribute('data-tool', name);

  var spinner = document.createElement('span');
  spinner.className = 'tc-spinner';
  span.appendChild(spinner);
  span.appendChild(document.createTextNode(' ' + name));

  return span;
}

function updateToolPill(pill, status, name) {
  pill.className = createToolPillClass(status);
  pill.textContent = createToolPillText(status, name);
}

export function registerToolCallRenderer() {
  StreamDispatcher.on('tool_call', function(dataStr, ctx) {
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
          var span = createCallingPill(info.name);
          span.setAttribute('data-id', info.id);
          tcEl.appendChild(span);
          logUI('tool_calling', info.name);
        }
      } else {
        if (existing) {
          updateToolPill(existing, info.status, info.name);
          logUI('tool_' + info.status, info.name);
        } else {
          var span2 = document.createElement('span');
          span2.className = createToolPillClass(info.status);
          span2.setAttribute('data-id', info.id);
          span2.textContent = createToolPillText(info.status, info.name);
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
