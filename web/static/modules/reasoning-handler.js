import C from './dom-contracts.js';
import { logUI } from './log-ui.js';
import { KairosStream } from './stream-dispatcher.js';

export function registerReasoningHandler() {
  KairosStream.on('reasoning', function(token, ctx) {
    try {
      var state = ctx;
      if (ctx && typeof ctx.getReasoningState === 'function') {
        state = {
          reasoningEls: ctx.getReasoningEls(),
          asstDiv: ctx.getAsstDiv(),
          bodyDivs: ctx.getBodyDivs(),
          reasoningState: ctx.getReasoningState(),
          reasoningText: ctx.getReasoningText(),
          context: ctx
        };
      }

      state.reasoningText += token;
      if (state.context) {
        state.context.appendReasoningText(token);
      }
      var isNewPhase = state.reasoningState.enter();
      if (isNewPhase) {
        // A new reasoning phase after a tool turn means the tool turn
        // is consumed by the reasoning transition — don't double-count it
        // in getPhaseIndex.
        if (state.context && state.context.getToolTurnSinceLastContent()) {
          state.context.consumeToolTurn();
        }
        var newDet = document.createElement('details');
        newDet.className = C.REASONING;
        newDet.open = true;
        var summary = document.createElement('summary');
        summary.textContent = 'Razonando...';
        var rt = document.createElement('div');
        rt.className = C.RT;
        newDet.appendChild(summary);
        newDet.appendChild(rt);

        if (state.reasoningEls.length > 0) {
          var prev = state.reasoningEls[state.reasoningEls.length - 1];
          prev.querySelector('summary').textContent = 'Razonamiento';
          prev.open = false;
          state.asstDiv.appendChild(newDet);
        } else {
          state.bodyDivs[0].insertAdjacentElement('beforebegin', newDet);
        }
        state.reasoningEls.push(newDet);
        logUI('reasoning_phase', state.reasoningEls.length);
      }
      var rt = state.reasoningEls[state.reasoningEls.length - 1].querySelector('.' + C.RT);
      if (rt) rt.textContent += token;
    } catch (e) {
      console.error('Reasoning handler error:', e);
    }
  });
}

registerReasoningHandler();
