/**
 * Kairos Widgets — Widget Detector
 *
 * Listens to KairosStream 'content' events, detects widget markers in the
 * accumulated text, and emits 'widget:detected' events for logging/debugging.
 *
 * Does NOT create DOM elements.
 * Does NOT populate KairosWidgets.registry.
 */
import { KairosStream } from '../stream-dispatcher.js';

export function registerWidgetDetector() {
  KairosStream.on('content', function(token, state) {
    try {
      if (!state || !state.bodyDivs) return;

      if (state._toolTurnSinceLastContent) {
        state._toolTurnSinceLastContent = false;
        state._toolPhase = (state._toolPhase || 0) + 1;
      }
      var phaseIdx = Math.max(0, state.reasoningEls.length - 1) + (state._toolPhase || 0);

      if (!state.bodyDivs[phaseIdx]) return;

      state._widgetDetectCache = state._widgetDetectCache || {};
      var phaseCache = state._widgetDetectCache[phaseIdx] || {};

      var fullText = state.contentTexts[phaseIdx] || '';
      if (!fullText) return;

      var widgetRegex = /```html-widget(?:\s+([\w\-]+))?\s*\n([\s\S]*?)\n```/g;
      var tagRegex = /\[Widget:?\s*([\w\-]+)\]/gi;
      var rawMatches = [];
      var match;

      while ((match = widgetRegex.exec(fullText)) !== null) {
        rawMatches.push({
          index: match.index,
          end: match.index + match[0].length,
          key: match[1] || null,
          code: match[2],
          full: match[0]
        });
      }

      while ((match = tagRegex.exec(fullText)) !== null) {
        rawMatches.push({
          index: match.index,
          end: match.index + match[0].length,
          key: match[1],
          code: '',
          full: match[0],
          fromTag: true
        });
      }

      rawMatches.sort(function(a, b) {
        if (a.key && b.key && a.key === b.key) return (b.code ? 1 : 0) - (a.code ? 1 : 0);
        return a.index - b.index;
      });

      var filtered = [];
      var lastEnd = 0;
      var seenKeys = {};
      for (var m = 0; m < rawMatches.length; m++) {
        var mm = rawMatches[m];
        if (mm.index < lastEnd) continue;
        if (mm.key && seenKeys[mm.key]) continue;
        if (mm.key) seenKeys[mm.key] = true;
        filtered.push(mm);
        lastEnd = mm.end;
      }

      for (var i = 0; i < filtered.length; i++) {
        var wm = filtered[i];
        if (phaseCache[wm.index]) continue;
        phaseCache[wm.index] = true;

        KairosStream.emit('widget:detected', {
          key: wm.key,
          code: wm.code,
          bodyDiv: state.bodyDivs[phaseIdx],
          phaseIdx: phaseIdx
        });
      }

      state._widgetDetectCache[phaseIdx] = phaseCache;
    } catch (e) {
      console.error('Widget detector error:', e);
    }
  });
}

registerWidgetDetector();
