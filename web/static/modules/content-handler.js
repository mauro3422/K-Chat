export function registerContentHandler() {
  if (typeof KairosStream === 'undefined') return;

  KairosStream.on('content', function(token, state) {
    try {
      if (!state || !state.bodyDivs) {
        logUI('content_no_state', 'token=' + String(token).substring(0, 40));
        return;
      }
      
      var phaseIdx = Math.max(0, state.reasoningEls.length - 1);
      
      state.widgetMap = state.widgetMap || [];
      state.widgetMap[phaseIdx] = state.widgetMap[phaseIdx] || {};
      
      while (state.bodyDivs.length <= phaseIdx) {
        var newBody = document.createElement('div');
        newBody.className = 'msg-body md-content';
        var lastDet = state.reasoningEls[state.reasoningEls.length - 1];
        if (lastDet) {
          lastDet.insertAdjacentElement('afterend', newBody);
        } else {
          state.asstDiv.appendChild(newBody);
        }
        state.bodyDivs.push(newBody);
        state.contentTexts.push('');
        state.widgetMap[phaseIdx] = state.widgetMap[phaseIdx] || {};
      }
      
      if (!state.contentTexts[phaseIdx]) logUI('body_start', token.substring(0, 60));
      state.contentTexts[phaseIdx] += token;
      
      var fullText = state.contentTexts[phaseIdx];
      var widgetRegex = /```html-widget(?:\s+([\w\-]+))?\s*\n([\s\S]*?)\n```/g;
      var tagRegex = /\[Widget:?\s*([\w\-]+)\]/gi;
      var matches = [];
      var match;
      
      while ((match = widgetRegex.exec(fullText)) !== null) {
        matches.push({
          index: match.index,
          end: match.index + match[0].length,
          key: match[1] || null,
          code: match[2],
          full: match[0]
        });
      }
      
      while ((match = tagRegex.exec(fullText)) !== null) {
        matches.push({
          index: match.index,
          end: match.index + match[0].length,
          key: match[1],
          code: "",
          full: match[0],
          fromTag: true
        });
      }
      
      matches.sort(function(a, b) {
        if (a.key && b.key && a.key === b.key) return (b.code ? 1 : 0) - (a.code ? 1 : 0);
        return a.index - b.index;
      });
      var filteredMatches = [];
      var lastEnd = 0;
      var seenKeys = {};
      for (var m = 0; m < matches.length; m++) {
        var mm = matches[m];
        if (mm.index < lastEnd) continue;
        if (mm.key && seenKeys[mm.key]) continue;
        if (mm.key) seenKeys[mm.key] = true;
        filteredMatches.push(mm);
        lastEnd = mm.end;
      }
      matches = filteredMatches;
      
      var bodyDiv = state.bodyDivs[phaseIdx];
      var widgetMap = state.widgetMap[phaseIdx];
      
      var children = Array.prototype.slice.call(bodyDiv.children);
      for (var c = 0; c < children.length; c++) {
        var child = children[c];
        if (!child.classList.contains('msg-text-segment') && !child.classList.contains('interactive-widget-container')) {
          bodyDiv.removeChild(child);
        }
      }
      
      var expectedCount = matches.length * 2 + 1;
      
      while (bodyDiv.children.length < expectedCount) {
        var newIdx = bodyDiv.children.length;
        if (newIdx % 2 === 0) {
          var txtSeg = document.createElement('div');
          txtSeg.className = 'msg-text-segment';
          bodyDiv.appendChild(txtSeg);
        } else {
          var widgetIdx = Math.floor(newIdx / 2);
          var wm = matches[widgetIdx];
          var widgetId = 'widget-' + KairosWidgets.nextIndex();
          KairosWidgets.registry[widgetId] = wm.code;
          widgetMap[wm.index] = widgetId;
          
          var container = document.createElement('div');
          container.className = 'interactive-widget-container';
          container.setAttribute('data-widget-id', widgetId);
          if (wm.key) {
            container.setAttribute('data-widget-key', wm.key);
          }
          bodyDiv.appendChild(container);
          
          logUI('widget_added', widgetId + ' code=' + wm.code.length + 'b');
        }
      }
      
      while (bodyDiv.children.length > expectedCount) {
        bodyDiv.removeChild(bodyDiv.lastChild);
      }
      
      for (var i = 0; i <= matches.length; i++) {
        var start = i === 0 ? 0 : matches[i - 1].end;
        var end = i === matches.length ? fullText.length : matches[i].index;
        var segmentText = fullText.substring(start, end);
        
        var targetSeg = bodyDiv.children[i * 2];
        if (!targetSeg) continue;
        
        var incompleteWidget = null;
        if (i === matches.length) {
          incompleteWidget = segmentText.match(/```html-widget(?:\s+[\w\-]+)?\s*\n([\s\S]*)$/);
        }
        
        var cacheKey = segmentText;
        if (targetSeg.dataset.rawText === cacheKey) {
          continue;
        }
        targetSeg.dataset.rawText = cacheKey;
        
        if (incompleteWidget) {
          var beforeIncomplete = segmentText.substring(0, segmentText.length - incompleteWidget[0].length);
          var html = '';
          if (beforeIncomplete) {
            var parsedBefore = KairosMarkdown.parse(beforeIncomplete);
            if (typeof DOMPurify !== 'undefined') {
              html += DOMPurify.sanitize(parsedBefore);
            } else {
              html += beforeIncomplete;
              console.warn('DOMPurify not loaded, rendering as plain text');
            }
          }
          html += '<pre style="opacity:0.6"><code>' + KairosUtils.escHtml(incompleteWidget[0]) + '</code></pre>';
          targetSeg.innerHTML = html;
        } else {
          var parsedText = KairosMarkdown.parse(segmentText);
          if (typeof DOMPurify !== 'undefined') {
            targetSeg.innerHTML = DOMPurify.sanitize(parsedText);
          } else {
            targetSeg.textContent = segmentText;
            console.warn('DOMPurify not loaded, rendering as plain text');
          }
        }
      }
      
      KairosWidgets.initAll(bodyDiv);
    } catch (e) {
      console.error('Content handler error:', e);
    }
  });
}

registerContentHandler();
