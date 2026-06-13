import C from './dom-contracts.js';
import { processWidgetContainers } from './widget-container-renderer.js';
import { KairosWidgets } from './widgets/core.js';
import { initAll } from './widgets/iframe.js';
import { KairosMarkdown } from './markdown-renderer.js';
import { KairosUtils } from './utils.js';
import { KairosDebug } from '../debug.js';

function buildState(ctx) {
  if (!ctx || typeof ctx.getBodyDivs !== 'function') return null;
  var sharedKeys = ctx._renderedKeys || (ctx._renderedKeys = {});

  var state = {
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

  return state;
}

function ensureStateShape(state) {
  return state && state.bodyDivs && state.asstDiv;
}

function preparePhase(state, phaseIdx) {
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
}

function renderSegments(state, phaseIdx, fullText) {
  var widgetsApi = KairosWidgets;
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

  var result = processWidgetContainers(fullText, bodyDiv, existingByKey, state._renderedKeys);
  var textToRender = result.textToRender;
  var incompleteTail = result.incompleteTail;
  var widgetMatches = result.widgetMatches;

  for (var i = 0; i <= widgetMatches.length; i++) {
    var start = i === 0 ? 0 : widgetMatches[i - 1].end;
    var end = i === widgetMatches.length ? textToRender.length : widgetMatches[i].index;
    var segText = textToRender.substring(start, end);
    var segEl = bodyDiv.children[i * 2];
    if (!segEl) continue;
    var cacheKey = segText + '|' + incompleteTail + '|' + (i === widgetMatches.length ? '' : widgetMatches[i].key);
    if (segEl.dataset.rawText === cacheKey) continue;
    segEl.dataset.rawText = cacheKey;

    var purifyConfig = { ADD_TAGS: ['iframe'], ADD_ATTR: ['data-widget-id', 'data-widget-key'] };
    var html = '';
    if (segText && widgetsApi && widgetsApi.extract) {
      var extracted = widgetsApi.extract(segText);
      var parsed = KairosMarkdown.parse(extracted);
      html += typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(parsed, purifyConfig) : segText;
    } else if (segText) {
      var parsed = KairosMarkdown.parse(segText);
      html += typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(parsed, purifyConfig) : segText;
    }
    if (i === widgetMatches.length && incompleteTail) {
      html += '<pre style="opacity:0.6"><code>' + KairosUtils.escHtml(incompleteTail) + '</code></pre>';
    }
    segEl.innerHTML = html;
  }

  initAll(bodyDiv);
}

export function renderContentToken(ctx, token) {
  try {
    var state = buildState(ctx);
    if (!ensureStateShape(state)) {
      KairosDebug.logUI('content_no_state', 'token=' + String(token).substring(0, 40));
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
    preparePhase(state, phaseIdx);

    if (!state.contentTexts[phaseIdx]) KairosDebug.logUI('body_start', token.substring(0, 60));
    state.contentTexts[phaseIdx] += token;
    if (state.context) {
      state.context.appendContentText(phaseIdx, token);
    }
    state.reasoningState.exit();

    renderSegments(state, phaseIdx, state.contentTexts[phaseIdx]);
  } catch (e) {
    console.error('Content render error:', e);
  }
}
