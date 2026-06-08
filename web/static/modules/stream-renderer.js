(function() {
  if (typeof KairosStream === 'undefined') {
    console.error('KairosStream is not defined. Cannot initialize stream renderer.');
    return;
  }

  KairosStream.on('reasoning', function(token, state) {
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
  });

  KairosStream.on('content', function(token, state) {
    if (!state || !state.bodyDivs) {
      logUI('content_no_state', 'token=' + String(token).substring(0, 40));
      return;
    }
    
    var phaseIdx = Math.max(0, state.reasoningEls.length - 1);
    while (state.bodyDivs.length <= phaseIdx) {
      var newBody = document.createElement('div');
      newBody.className = 'msg-body md-content';
      var lastDet = state.reasoningEls[state.reasoningEls.length - 1];
      var nextEl = lastDet ? lastDet.nextSibling : null;
      if (nextEl && nextEl.classList && nextEl.classList.contains('tool-calls')) {
        nextEl.insertAdjacentElement('afterend', newBody);
      } else if (lastDet) {
        lastDet.insertAdjacentElement('afterend', newBody);
      } else {
        state.asstDiv.appendChild(newBody);
      }
      state.bodyDivs.push(newBody);
      state.contentTexts.push('');
      state.widgetMap = state.widgetMap || [];
      state.widgetMap[phaseIdx] = state.widgetMap[phaseIdx] || {};
    }
    if (!state.contentTexts[phaseIdx]) logUI('body_start', token.substring(0, 60));
    state.contentTexts[phaseIdx] += token;
    
    var fullText = state.contentTexts[phaseIdx];
    var widgetRegex = /```html-widget\s*\n([\s\S]*?)\n```/g;
    var matches = [];
    var match;
    
    while ((match = widgetRegex.exec(fullText)) !== null) {
      matches.push({
        index: match.index,
        end: match.index + match[0].length,
        code: match[1],
        full: match[0]
      });
    }
    
    var bodyDiv = state.bodyDivs[phaseIdx];
    var widgetMap = state.widgetMap[phaseIdx];
    var existingWidgets = bodyDiv.querySelectorAll('.interactive-widget-container');
    
    // Detectar si hay un widget incompleto (aún no se cerró el ```)
    var lastMatch = matches.length > 0 ? matches[matches.length - 1] : null;
    var remaining = fullText.substring(lastMatch ? lastMatch.end : 0);
    var incompleteWidget = remaining.match(/```html-widget\s*\n([\s\S]*)$/);
    
    // Si hay widgets nuevos completos, agregarlos
    if (matches.length > existingWidgets.length) {
      for (var i = existingWidgets.length; i < matches.length; i++) {
        var m = matches[i];
        var widgetId = 'widget-' + KairosWidgets.index++;
        KairosWidgets.registry[widgetId] = m.code;
        widgetMap[m.index] = widgetId;
        
        var container = document.createElement('div');
        container.className = 'interactive-widget-container';
        container.setAttribute('data-widget-id', widgetId);
        bodyDiv.appendChild(container);
        
        logUI('widget_added', widgetId + ' code=' + m.code.length + 'b');
      }
      
      // Inicializar solo los widgets nuevos (initAll respeta el flag data-initialized)
      KairosWidgets.initAll(bodyDiv);
    }
    
    // Actualizar el progreso
    var progressDiv = bodyDiv.querySelector('.stream-progress');
    if (!progressDiv) {
      progressDiv = document.createElement('div');
      progressDiv.className = 'stream-progress';
      bodyDiv.appendChild(progressDiv);
    }
    
    if (incompleteWidget) {
      // Mostrar código en progreso con opacidad 0.6
      var beforeIncomplete = remaining.substring(0, remaining.length - incompleteWidget[0].length);
      var html = '';
      if (beforeIncomplete) {
        var parsedBefore = KairosMarkdown.parse(beforeIncomplete);
        html += (typeof DOMPurify !== 'undefined') ? DOMPurify.sanitize(parsedBefore) : parsedBefore;
      }
      html += '<pre style="opacity:0.6"><code>' + KairosUtils.escHtml(incompleteWidget[0]) + '</code></pre>';
      progressDiv.innerHTML = html;
    } else if (remaining) {
      // Mostrar markdown normal
      var parsedRemaining = KairosMarkdown.parse(remaining);
      progressDiv.innerHTML = (typeof DOMPurify !== 'undefined') ? DOMPurify.sanitize(parsedRemaining) : parsedRemaining;
    } else {
      progressDiv.innerHTML = '';
    }
  });

  KairosStream.on('tool_call', function(dataStr, state) {
    var info = JSON.parse(dataStr);
    if (info.status === 'partial') return;
    var allTc = state.asstDiv.querySelectorAll('.tool-calls');
    var tcEl = null;
    if (info.status === 'calling') {
      var foundIn = null;
      for (var ti = 0; ti < allTc.length; ti++) {
        if (allTc[ti].querySelector('[data-id="' + info.id + '"]')) { foundIn = allTc[ti]; break; }
      }
      if (foundIn) {
        tcEl = foundIn;
      } else if (allTc.length < state.reasoningEls.length) {
        tcEl = document.createElement('div');
        tcEl.className = 'tool-calls';
        var lastDet = state.reasoningEls[state.reasoningEls.length - 1];
        lastDet.insertAdjacentElement('afterend', tcEl);
        logUI('tool_calls_seq', state.reasoningEls.length);
      } else if (allTc.length > 0) {
        tcEl = allTc[allTc.length - 1];
      } else {
        tcEl = document.createElement('div');
        tcEl.className = 'tool-calls';
        state.bodyDivs[0].insertAdjacentElement('beforebegin', tcEl);
        logUI('tool_calls_seq', 0);
      }
    } else {
      for (var ti2 = 0; ti2 < allTc.length; ti2++) {
        if (allTc[ti2].querySelector('[data-id="' + info.id + '"]')) { tcEl = allTc[ti2]; break; }
      }
      if (!tcEl && allTc.length > 0) tcEl = allTc[allTc.length - 1];
    }
    if (!tcEl) return;
    var existing = tcEl.querySelector('[data-id="' + info.id + '"]');
    if (info.status === 'calling') {
      if (!existing) {
        var span = document.createElement('span');
        span.className = 'tc-item calling';
        span.setAttribute('data-id', info.id);
        span.setAttribute('data-tool', info.name);
        span.innerHTML = '<span class="tc-spinner"></span> ' + KairosUtils.escHtml(info.name);
        tcEl.appendChild(span);
        logUI('tool_calling', info.name);
      }
    } else {
      if (existing) {
        existing.className = 'tc-item ' + info.status;
        existing.innerHTML = (info.status === 'ok' ? '&#10003; ' : '&#10007; ') + info.name;
        logUI('tool_' + info.status, info.name);
      } else {
        var span2 = document.createElement('span');
        span2.className = 'tc-item ' + info.status;
        span2.setAttribute('data-id', info.id);
        span2.innerHTML = (info.status === 'ok' ? '&#10003; ' : '&#10007; ') + (info.name || '?');
        tcEl.appendChild(span2);
        logUI('tool_' + info.status, info.name);
      }
    }
  });
})();
