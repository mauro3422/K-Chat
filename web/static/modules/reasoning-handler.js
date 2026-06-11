import C from './dom-contracts.js';

export function registerReasoningHandler() {
  if (typeof KairosStream === 'undefined') return;

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
        var newDet = document.createElement('details');
        newDet.className = C.REASONING;
        newDet.open = true;
        newDet.innerHTML = '<summary>Razonando...</summary><div class="' + C.RT + '"></div>';

        if (state.reasoningEls.length > 0) {
          var prev = state.reasoningEls[state.reasoningEls.length - 1];
          prev.querySelector('summary').textContent = 'Razonamiento';
          prev.open = false;
          state.asstDiv.appendChild(newDet);
          state.reasoningEls.push(newDet);
          logUI('reasoning_phase', state.reasoningEls.length);
        } else {
          state.bodyDivs[0].insertAdjacentElement('beforebegin', newDet);
          state.reasoningEls.push(newDet);
          logUI('reasoning_phase', state.reasoningEls.length);
        }
      }
      var rt = state.reasoningEls[state.reasoningEls.length - 1].querySelector('.' + C.RT);
      if (rt) rt.textContent += token;
    } catch (e) {
      console.error('Reasoning handler error:', e);
    }
  });
}

registerReasoningHandler();
