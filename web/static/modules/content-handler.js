import C from './dom-contracts.js';

export function registerContentHandler() {
  if (typeof KairosStream === 'undefined') return;

  KairosStream.on('content', function(token, ctx) {
    try {
      var sharedKeys = ctx._renderedKeys || (ctx._renderedKeys = {});
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
          context: ctx,
          _renderedKeys: sharedKeys
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
        newBody.className = C.MSG_BODY_MD();
        state.asstDiv.appendChild(newBody);
        state.bodyDivs.push(newBody);
        state.contentTexts.push('');
        if (state.context) {
          state.context.ensureBodyDiv(phaseIdx, C.MSG_BODY_MD());
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

      var targetSeg = bodyDiv.querySelector('.' + C.MSG_TEXT_SEGMENT);
      if (!targetSeg) {
        targetSeg = document.createElement('div');
        targetSeg.className = C.MSG_TEXT_SEGMENT;
        bodyDiv.appendChild(targetSeg);
      }

      var children = Array.prototype.slice.call(bodyDiv.children);
      for (var c = 0; c < children.length; c++) {
        if (children[c] !== targetSeg) {
          bodyDiv.removeChild(children[c]);
        }
      }
      if (!targetSeg) return;

      state._renderedKeys = state._renderedKeys || {};
      var widgetMatches = [];
      var tagRegex = /\[Widget:?\s*([\w\-]+)\]/gi;
      var m;
      while ((m = tagRegex.exec(fullText)) !== null) {
        widgetMatches.push({ index: m.index, end: m.index + m[0].length, key: m[1], isNew: !state._renderedKeys[m[1]] });
        state._renderedKeys[m[1]] = true;
      }

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

      var expectedCount = widgetMatches.length * 2 + 1;
      while (bodyDiv.children.length < expectedCount) {
        var newIdx = bodyDiv.children.length;
        if (newIdx % 2 === 0) {
          var seg = document.createElement('div');
          seg.className = C.MSG_TEXT_SEGMENT;
          bodyDiv.appendChild(seg);
        } else {
          var wm = widgetMatches[(newIdx - 1) / 2];
          if (wm.isNew) {
            var wid = 'widget-' + KairosWidgets.nextIndex();
            KairosWidgets.registry[wid] = '';
            var con = document.createElement('div');
            con.className = C.WIDGET_CONTAINER;
            con.setAttribute('data-widget-id', wid);
            con.setAttribute('data-widget-key', wm.key);
            bodyDiv.appendChild(con);
          } else {
            var ph = document.createElement('div');
            ph.style.display = 'none';
            bodyDiv.appendChild(ph);
          }
        }
      }

      while (bodyDiv.children.length > expectedCount) {
        bodyDiv.removeChild(bodyDiv.lastChild);
      }

      for (var i = 0; i <= widgetMatches.length; i++) {
        var start = i === 0 ? 0 : widgetMatches[i - 1].end;
        var end = i === widgetMatches.length ? textToRender.length : widgetMatches[i].index;
        var segText = textToRender.substring(start, end);
        var targetSeg = bodyDiv.children[i * 2];
        if (!targetSeg) continue;
        var cacheKey = segText + '|' + incompleteTail + '|' + (i === widgetMatches.length ? '' : widgetMatches[i].key);
        if (targetSeg.dataset.rawText === cacheKey) continue;
        targetSeg.dataset.rawText = cacheKey;

        var purifyConfig = { ADD_TAGS: ['iframe'], ADD_ATTR: ['data-widget-id', 'data-widget-key'] };
        var html = '';
        if (segText && typeof KairosWidgets !== 'undefined' && KairosWidgets.extract) {
          var extracted = KairosWidgets.extract(segText);
          var parsed = KairosMarkdown.parse(extracted);
          if (typeof DOMPurify !== 'undefined') {
            html += DOMPurify.sanitize(parsed, purifyConfig);
          } else {
            html += segText;
          }
        } else if (segText) {
          var parsed = KairosMarkdown.parse(segText);
          if (typeof DOMPurify !== 'undefined') {
            html += DOMPurify.sanitize(parsed, purifyConfig);
          } else {
            html += segText;
          }
        }
        if (i === widgetMatches.length && incompleteTail) {
          html += '<pre style="opacity:0.6"><code>' + KairosUtils.escHtml(incompleteTail) + '</code></pre>';
        }
        targetSeg.innerHTML = html;
      }

      if (typeof KairosWidgets !== 'undefined' && typeof KairosWidgets.initAll === 'function') {
        KairosWidgets.initAll(bodyDiv);
      }
    } catch (e) {
      console.error('Content handler error:', e);
    }
  });
}

registerContentHandler();
