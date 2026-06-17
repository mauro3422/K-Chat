import C from './dom-contracts.js';
import { getLogger } from './logger.js';
import { logUI } from './log-ui.js';
import { processWidgetContainers } from './widget-container-renderer.js';
import { StreamDispatcher } from './stream-dispatcher.js';
import { WidgetManager } from './widgets/core.js';
import { initAll } from './widgets/iframe.js';
import { MarkdownRenderer } from './markdown-renderer.js';
import { Utils } from './utils.js';
var log = getLogger('content-handler');

function setSegmentContent(targetSeg, html, incompleteTail) {
  if (!targetSeg) return;
  var renderedHtml = html || '';
  if (incompleteTail) {
    renderedHtml += '<pre style="opacity:0.6"><code>' + Utils.escHtml(incompleteTail) + '</code></pre>';
  }

  var fragment = null;
  if (typeof document.createRange === 'function') {
    var range = document.createRange();
    if (range && typeof range.createContextualFragment === 'function') {
      fragment = range.createContextualFragment(renderedHtml);
    }
  }

  if (!fragment) {
    fragment = document.createDocumentFragment();
    var holder = document.createElement('div');
    holder.textContent = renderedHtml;
    fragment.appendChild(holder);
  }

  if (typeof targetSeg.replaceChildren === 'function') {
    targetSeg.replaceChildren(fragment);
    return;
  }

  if (typeof targetSeg.appendChild === 'function') {
    while (targetSeg.firstChild) {
      targetSeg.removeChild(targetSeg.firstChild);
    }
    targetSeg.appendChild(fragment);
  }
}

export function registerContentHandler() {

  StreamDispatcher.on('content', function(token, ctx) {
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

      var widgetsApi = WidgetManager;

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

      var existingByKey = {};
      for (var ci = 1; ci < bodyDiv.children.length; ci += 2) {
        var ch = bodyDiv.children[ci];
        if (ch && ch.className === C.WIDGET_CONTAINER) {
          var key = ch.getAttribute('data-widget-key');
          if (key) existingByKey[key] = ch;
        }
      }

      var children = Array.prototype.slice.call(bodyDiv.children);
      for (var c = 0; c < children.length; c++) {
        if (children[c] !== targetSeg) {
          bodyDiv.removeChild(children[c]);
        }
      }
      if (!targetSeg) return;

      state._renderedKeys = state._renderedKeys || {};

      var result = processWidgetContainers(fullText, bodyDiv, existingByKey, state._renderedKeys);
      var textToRender = result.textToRender;
      var incompleteTail = result.incompleteTail;
      var widgetMatches = result.widgetMatches;

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
        if (segText && widgetsApi && widgetsApi.extract) {
          var extracted = widgetsApi.extract(segText);
          var parsed = MarkdownRenderer.parse(extracted);
          if (typeof DOMPurify !== 'undefined') {
            html += DOMPurify.sanitize(parsed, purifyConfig);
          } else {
            html += segText;
          }
        } else if (segText) {
          var parsed = MarkdownRenderer.parse(segText);
          if (typeof DOMPurify !== 'undefined') {
            html += DOMPurify.sanitize(parsed, purifyConfig);
          } else {
            html += segText;
          }
        }
        setSegmentContent(targetSeg, html, i === widgetMatches.length ? incompleteTail : '');
      }

      initAll(bodyDiv);
    } catch (e) {
      console.error('Content handler error:', e);
    }
  });

  // ── Memory events: auto-retrieved memories ────────────────────────
  StreamDispatcher.on('memory', function(data, ctx) {
    try {
      var asstDiv = ctx && (typeof ctx.getAsstDiv === 'function' ? ctx.getAsstDiv() : ctx.asstDiv);
      if (!asstDiv) return;

      // Create details element (same style as reasoning, green tint)
      var details = document.createElement('details');
      details.className = 'reasoning memories-phase';
      details.open = true;
      var summary = document.createElement('summary');
      summary.textContent = '📖 Memorias';
      details.appendChild(summary);
      var rt = document.createElement('div');
      rt.className = 'rt memory-content';
      rt.textContent = data || '';
      details.appendChild(rt);

      // Insert at the top of the message (before reasoning/content)
      if (asstDiv.firstChild) {
        asstDiv.insertBefore(details, asstDiv.firstChild);
      } else {
        asstDiv.appendChild(details);
      }
    } catch (e) {
      console.error('Memory handler error:', e);
    }
  });
}

registerContentHandler();
