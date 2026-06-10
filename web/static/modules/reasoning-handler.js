/* global logUI */

export function registerReasoningHandler() {
  if (typeof KairosStream === 'undefined') return;

  KairosStream.on('reasoning', function(token, state) {
    try {
      state.reasoningText += token;
      var toolCount = state.asstDiv.querySelectorAll('.tool-calls').length;
      if (state.reasoningEls.length <= toolCount) {
        var newDet = document.createElement('details');
        newDet.className = 'reasoning';
        newDet.open = true;
        newDet.innerHTML = '<summary>Razonando...</summary><div class="rt"></div>';

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
      var rt = state.reasoningEls[state.reasoningEls.length - 1].querySelector('.rt');
      if (rt) rt.textContent += token;
    } catch (e) {
      console.error('Reasoning handler error:', e);
    }
  });
}

registerReasoningHandler();
