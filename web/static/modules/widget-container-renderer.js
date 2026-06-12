import C from './dom-contracts.js';
import { getLogger } from './logger.js';
import { KairosWidgets } from './widgets/core.js';

var log = getLogger('widget-container-renderer');

export function processWidgetContainers(fullText, bodyDiv, existingByKey, renderedKeys) {
  var widgetsApi = globalThis.KairosWidgets || KairosWidgets;
  // Find all standard code blocks and inline code blocks that are NOT widgets
  var ignoredRanges = [];
  var ignoredCodeBlockRegex = /```(?!html-widget)[\s\S]*?(?:```|$)/g;
  var match;
  while ((match = ignoredCodeBlockRegex.exec(fullText)) !== null) {
    ignoredRanges.push({ start: match.index, end: match.index + match[0].length });
  }
  var inlineRegex = /`[^`\n]+`/g;
  while ((match = inlineRegex.exec(fullText)) !== null) {
    ignoredRanges.push({ start: match.index, end: match.index + match[0].length });
  }

  function isIgnored(idx) {
    for (var i = 0; i < ignoredRanges.length; i++) {
      var range = ignoredRanges[i];
      if (idx >= range.start && idx < range.end) {
        return true;
      }
    }
    return false;
  }

  var widgetMatches = [];
  var tagRegex = /\[Widget:?\s*([\w\-]+)\]/gi;
  var m;
  while ((m = tagRegex.exec(fullText)) !== null) {
    if (!isIgnored(m.index)) {
      widgetMatches.push({ index: m.index, end: m.index + m[0].length, key: m[1], isNew: !renderedKeys[m[1]], codeBlock: false });
      renderedKeys[m[1]] = true;
    }
  }

  var codeBlockRegex = /```html-widget(?:\s+([\w\-]+))?\s*\n([\s\S]*?)\n```/g;
  while ((m = codeBlockRegex.exec(fullText)) !== null) {
    if (!isIgnored(m.index)) {
      var cKey = m[1] || null;
      var innerCode = m[2] || '';
      var dedupKey = cKey || '_pos_' + m.index;
      widgetMatches.push({ index: m.index, end: m.index + m[0].length, key: cKey, code: innerCode, isNew: !renderedKeys[dedupKey], codeBlock: true });
      renderedKeys[dedupKey] = true;
    }
  }

  widgetMatches.sort(function(a, b) { return a.index - b.index; });
  var filteredMatches = [];
  var lastEnd = 0;
  for (var fm = 0; fm < widgetMatches.length; fm++) {
    if (widgetMatches[fm].index >= lastEnd) {
      filteredMatches.push(widgetMatches[fm]);
      lastEnd = widgetMatches[fm].end;
    }
  }
  widgetMatches = filteredMatches;

  // High-frequency logs commented out to save CPU cycles/TDP on SUMA C10
  // if (widgetMatches.length) {
  //   log.info('matches', { count: widgetMatches.length, types: widgetMatches.map(function(w){ return (w.codeBlock ? 'cb' : 'tag') + '=' + (w.key || 'anon') + ' new=' + w.isNew; }).join(', ') });
  // }

  var textToRender = fullText;
  var incompleteTail = '';

  var lastOpen = fullText.lastIndexOf('```html-widget');
  if (lastOpen >= 0 && !isIgnored(lastOpen)) {
    var afterOpen = fullText.substring(lastOpen);
    var completeBlock = afterOpen.match(/^```html-widget(?:\s+[\w\-]+)?\s*\n[\s\S]*?\n```/);
    if (!completeBlock) {
      textToRender = fullText.substring(0, lastOpen);
      incompleteTail = fullText.substring(lastOpen);
      // log.debug('incomplete_cb', { tailLen: incompleteTail.length });
    }
  }

  for (var wmi = 0; wmi < widgetMatches.length; wmi++) {
    var wmm = widgetMatches[wmi];
    if (wmm.codeBlock && textToRender.length >= wmm.end) {
      textToRender = textToRender.substring(0, wmm.index) + textToRender.substring(wmm.end);
      var shift = wmm.end - wmm.index;
      wmm.end = wmm.index;
      for (var adj = wmi + 1; adj < widgetMatches.length; adj++) {
        widgetMatches[adj].index -= shift;
        widgetMatches[adj].end -= shift;
      }
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
      var lookupKey = wm.key || (wm.codeBlock ? '_pos_' + (wm.index || 0) : null);
      var existing = lookupKey ? existingByKey[lookupKey] : null;
      if (existing) {
        bodyDiv.appendChild(existing);
        log.debug('reuse_container', { key: lookupKey, wid: existing.getAttribute('data-widget-id') });
      } else if (wm.isNew) {
        var wid = 'widget-' + widgetsApi.nextIndex();
        widgetsApi.registry[wid] = wm.code || '';
        var con = document.createElement('div');
        con.className = C.WIDGET_CONTAINER;
        con.setAttribute('data-widget-id', wid);
        if (lookupKey) con.setAttribute('data-widget-key', lookupKey);
        bodyDiv.appendChild(con);
        log.info('new_container', { wid: wid, key: lookupKey, codeLen: (wm.code || '').length });
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

  return { textToRender: textToRender, incompleteTail: incompleteTail, widgetMatches: widgetMatches };
}
