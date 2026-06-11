export function registerContentHandler() {
  if (typeof KairosStream === 'undefined') return;

  KairosStream.on('content', function(token, ctx) {
    try {
      var state = ctx;
      if (ctx && typeof ctx.getBodyDivs === 'function') {
        state = {
          bodyDivs: ctx.getBodyDivs(),
          asstDiv: ctx.getAsstDiv(),
          contentTexts: [],
          reasoningEls: ctx.getReasoningEls(),
          reasoningState: ctx.getReasoningState(),
          _toolPhase: ctx.getToolPhase(),
          _toolTurnSinceLastContent: ctx.getToolTurnSinceLastContent(),
          getPhaseIdx: function() { return ctx.getPhaseIndex(); },
          context: ctx
        };
        for (var i = 0; i < state.bodyDivs.length; i++) {
          state.contentTexts.push(ctx.getContentText(i));
        }
      }

      if (!state || !state.bodyDivs) {
        logUI('content_no_state', 'token=' + String(token).substring(0, 40));
        return;
      }

      if (state._toolTurnSinceLastContent) {
        state._toolTurnSinceLastContent = false;
        state._toolPhase = (state._toolPhase || 0) + 1;
        if (state.context) {
          state.context.enterToolPhase();
        }
      }
      var phaseIdx = state.getPhaseIdx ? state.getPhaseIdx() : (Math.max(0, state.reasoningEls.length - 1) + (state._toolPhase || 0));

      while (state.bodyDivs.length <= phaseIdx) {
        var newBody = document.createElement('div');
        newBody.className = 'msg-body md-content';
        state.asstDiv.appendChild(newBody);
        state.bodyDivs.push(newBody);
        state.contentTexts.push('');
        if (state.context) {
          state.context.ensureBodyDiv(phaseIdx, 'msg-body md-content');
        }
      }

      if (!state.contentTexts[phaseIdx]) logUI('body_start', token.substring(0, 60));
      state.contentTexts[phaseIdx] += token;
      if (state.context) {
        state.context.appendContentText(phaseIdx, token);
      }
      state.reasoningState.exit();

      var fullText = state.contentTexts[phaseIdx];
      var bodyDiv = state.bodyDivs[phaseIdx];

      var children = Array.prototype.slice.call(bodyDiv.children);
      for (var c = 0; c < children.length; c++) {
        var child = children[c];
        if (!child.classList.contains('msg-text-segment')) {
          bodyDiv.removeChild(child);
        }
      }

      while (bodyDiv.children.length < 1) {
        var txtSeg = document.createElement('div');
        txtSeg.className = 'msg-text-segment';
        bodyDiv.appendChild(txtSeg);
      }

      while (bodyDiv.children.length > 1) {
        bodyDiv.removeChild(bodyDiv.lastChild);
      }

      var targetSeg = bodyDiv.children[0];
      if (!targetSeg) return;

      var textToRender = fullText;
      var incompleteTail = '';

      var lastOpen = fullText.lastIndexOf('```html-widget');
      if (lastOpen >= 0) {
        var afterOpen = fullText.substring(lastOpen);
        var completeBlock = afterOpen.match(/^```html-widget(?:\s+[\w\-]+)?\s*\n[\s\S]*?\n```/);
        if (!completeBlock) {
          textToRender = fullText.substring(0, lastOpen);
          incompleteTail = fullText.substring(lastOpen);
        }
      }

      var cacheKey = textToRender + '|' + incompleteTail;
      if (targetSeg.dataset.rawText === cacheKey) {
        return;
      }
      targetSeg.dataset.rawText = cacheKey;

      var html = '';
      if (textToRender && typeof KairosWidgets !== 'undefined' && KairosWidgets.extract) {
        var extracted = KairosWidgets.extract(textToRender);
        var parsed = KairosMarkdown.parse(extracted);
        if (typeof DOMPurify !== 'undefined') {
          html += DOMPurify.sanitize(parsed);
        } else {
          html += textToRender;
          console.warn('DOMPurify not loaded, rendering as plain text');
        }
      } else if (textToRender) {
        parsed = KairosMarkdown.parse(textToRender);
        if (typeof DOMPurify !== 'undefined') {
          html += DOMPurify.sanitize(parsed);
        } else {
          html += textToRender;
        }
      }

      if (incompleteTail) {
        html += '<pre style="opacity:0.6"><code>' + KairosUtils.escHtml(incompleteTail) + '</code></pre>';
      }

      targetSeg.innerHTML = html;
    } catch (e) {
      console.error('Content handler error:', e);
    }
  });
}

registerContentHandler();
