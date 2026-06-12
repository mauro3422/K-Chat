import { describe, test, expect } from 'vitest';
import './setup.js';

var { StreamContext } = await import('../web/static/modules/stream-context.js');

function makeDom() {
  var asstDiv = document.createElement('div');
  asstDiv.className = 'assistant-message';

  var bodyDiv = document.createElement('div');
  bodyDiv.className = 'msg-body md-content';
  asstDiv.appendChild(bodyDiv);

  var seg = document.createElement('div');
  seg.className = 'msg-text-segment';
  bodyDiv.appendChild(seg);

  return { asstDiv: asstDiv, bodyDiv: bodyDiv };
}

function insertBeforeBody(asstDiv, el) {
  var body = asstDiv.querySelector('.msg-body');
  if (body) {
    body.insertAdjacentElement('beforebegin', el);
  } else {
    asstDiv.appendChild(el);
  }
}

function appendAfterAll(asstDiv, el) {
  asstDiv.appendChild(el);
}

function addReasoningEl(asstDiv, bodyDiv, reasoningEls, isFirst) {
  var newDet = document.createElement('details');
  newDet.className = 'reasoning';
  newDet.open = true;
  var sum = document.createElement('summary');
  sum.textContent = isFirst ? 'Razonando...' : 'Razonamiento';
  newDet.appendChild(sum);
  var rt = document.createElement('div');
  rt.className = 'rt';
  newDet.appendChild(rt);

  if (isFirst) {
    if (asstDiv.children.length > 1) {
      asstDiv.appendChild(newDet);
    } else {
      bodyDiv.insertAdjacentElement('beforebegin', newDet);
    }
  } else {
    var prev = reasoningEls[reasoningEls.length - 1];
    prev.open = false;
    asstDiv.appendChild(newDet);
  }
  reasoningEls.push(newDet);
  return newDet;
}

function addToolCall(asstDiv, reasoningEls, toolCallsContainers, info) {
  var tcEl = null;
  if (info.status === 'calling') {
    var foundIn = null;
    for (var ti = 0; ti < toolCallsContainers.length; ti++) {
      var existing = toolCallsContainers[ti].querySelector('[data-id="' + info.id + '"]');
      if (existing) { foundIn = toolCallsContainers[ti]; break; }
    }
    if (foundIn) {
      tcEl = foundIn;
    } else if (toolCallsContainers.length < reasoningEls.length) {
      tcEl = document.createElement('div');
      tcEl.className = 'tool-calls';
      asstDiv.appendChild(tcEl);
      toolCallsContainers.push(tcEl);
    } else if (toolCallsContainers.length > 0) {
      tcEl = toolCallsContainers[toolCallsContainers.length - 1];
    } else {
      tcEl = document.createElement('div');
      tcEl.className = 'tool-calls';
      asstDiv.appendChild(tcEl);
      toolCallsContainers.push(tcEl);
    }
    if (tcEl && !tcEl.querySelector('[data-id="' + info.id + '"]')) {
      var span = document.createElement('span');
      span.className = 'tc-item calling';
      span.setAttribute('data-id', info.id);
      span.setAttribute('data-tool', info.name);
      span.innerHTML = '<span class="tc-spinner"></span> ' + info.name;
      tcEl.appendChild(span);
    }
  } else {
    for (var t = 0; t < toolCallsContainers.length; t++) {
      var e = toolCallsContainers[t].querySelector('[data-id="' + info.id + '"]');
      if (e) { tcEl = toolCallsContainers[t]; break; }
    }
    if (!tcEl && toolCallsContainers.length > 0) tcEl = toolCallsContainers[toolCallsContainers.length - 1];
    if (tcEl) {
      var existingPill = tcEl.querySelector('[data-id="' + info.id + '"]');
      if (existingPill) {
        existingPill.className = 'tc-item ' + info.status;
        existingPill.innerHTML = (info.status === 'ok' ? '\u2713 ' : '\u2717 ') + info.name;
      } else {
        var span = document.createElement('span');
        span.className = 'tc-item ' + info.status;
        span.setAttribute('data-id', info.id);
        span.innerHTML = (info.status === 'ok' ? '\u2713 ' : '\u2717 ') + (info.name || '?');
        tcEl.appendChild(span);
      }
    }
  }
}

describe('DOM Ordering', () => {

  test('reasoning before content — first reasoning inserts before body', function() {
    var dom = makeDom();
    var reasoningEls = [];
    var toolCallsContainers = [];

    addReasoningEl(dom.asstDiv, dom.bodyDiv, reasoningEls, true);

    var bodyIdx = Array.prototype.indexOf.call(dom.asstDiv.children, dom.bodyDiv);
    var reIdx = Array.prototype.indexOf.call(dom.asstDiv.children, reasoningEls[0]);

    expect(reIdx).toBeGreaterThanOrEqual(0);
    expect(bodyIdx).toBeGreaterThanOrEqual(0);
    expect(reIdx).toBeLessThan(bodyIdx);
  });

  test('content before reasoning — first reasoning appends after tool-calls', function() {
    var dom = makeDom();
    var reasoningEls = [];
    var toolCallsContainers = [];

    // bodyDiv exists from makeDom; add tool-calls container first
    addToolCall(dom.asstDiv, reasoningEls, toolCallsContainers, { id: 'tc1', name: 'read_file', status: 'calling' });
    // Now add first reasoning (asstDiv has body + tool-calls, so children.length > 1)
    addReasoningEl(dom.asstDiv, dom.bodyDiv, reasoningEls, true);

    var bodyIdx = Array.prototype.indexOf.call(dom.asstDiv.children, dom.bodyDiv);
    var tcIdx = Array.prototype.indexOf.call(dom.asstDiv.children, toolCallsContainers[0]);
    var reIdx = Array.prototype.indexOf.call(dom.asstDiv.children, reasoningEls[0]);

    expect(bodyIdx).toBeGreaterThanOrEqual(0);
    expect(tcIdx).toBeGreaterThanOrEqual(0);
    expect(reIdx).toBeGreaterThanOrEqual(0);
    expect(reIdx).toBeGreaterThan(tcIdx);
    expect(tcIdx).toBeGreaterThan(bodyIdx);
  });

  test('tool loop with reasoning — correct chronological order', function() {
    var dom = makeDom();
    var reasoningEls = [];
    var toolCallsContainers = [];

    addReasoningEl(dom.asstDiv, dom.bodyDiv, reasoningEls, true);
    addToolCall(dom.asstDiv, reasoningEls, toolCallsContainers, { id: 'tc1', name: 'read_file', status: 'calling' });
    addToolCall(dom.asstDiv, reasoningEls, toolCallsContainers, { id: 'tc1', name: 'read_file', status: 'ok' });
    addReasoningEl(dom.asstDiv, dom.bodyDiv, reasoningEls, false);

    var bodyDivs = Array.prototype.filter.call(dom.asstDiv.children, function(c) { return c.className === 'msg-body md-content'; });
    var tcDivs = Array.prototype.filter.call(dom.asstDiv.children, function(c) { return c.className === 'tool-calls'; });
    var reDivs = Array.prototype.filter.call(dom.asstDiv.children, function(c) { return c.className === 'reasoning'; });

    expect(bodyDivs.length).toBe(1);
    expect(tcDivs.length).toBe(1);
    expect(reDivs.length).toBe(2);

    var bodyIdx0 = Array.prototype.indexOf.call(dom.asstDiv.children, bodyDivs[0]);
    var reIdx0 = Array.prototype.indexOf.call(dom.asstDiv.children, reDivs[0]);
    var tcIdx = Array.prototype.indexOf.call(dom.asstDiv.children, tcDivs[0]);
    var reIdx1 = Array.prototype.indexOf.call(dom.asstDiv.children, reDivs[1]);

    expect(reIdx0).toBeLessThan(bodyIdx0);
    expect(bodyIdx0).toBeLessThan(tcIdx);
    expect(tcIdx).toBeLessThan(reIdx1);
  });

  test('sequential tool calls with content — same container and order', function() {
    var dom = makeDom();
    var reasoningEls = [];
    var toolCallsContainers = [];

    addToolCall(dom.asstDiv, reasoningEls, toolCallsContainers, { id: 'tc1', name: 'fetch', status: 'calling' });
    addToolCall(dom.asstDiv, reasoningEls, toolCallsContainers, { id: 'tc1', name: 'fetch', status: 'ok' });
    addToolCall(dom.asstDiv, reasoningEls, toolCallsContainers, { id: 'tc2', name: 'read', status: 'calling' });
    addToolCall(dom.asstDiv, reasoningEls, toolCallsContainers, { id: 'tc2', name: 'read', status: 'ok' });

    var tcDivs = Array.prototype.filter.call(dom.asstDiv.children, function(c) { return c.className === 'tool-calls'; });
    expect(tcDivs.length).toBe(1);

    var pills = tcDivs[0].children;
    expect(pills.length).toBe(2);

    expect(pills[0].getAttribute('data-id')).toBe('tc1');
    expect(pills[0].className).toContain('ok');
    expect(pills[1].getAttribute('data-id')).toBe('tc2');
    expect(pills[1].className).toContain('ok');
  });

  test('empty stream produces only initial body div', function() {
    var dom = makeDom();
    expect(dom.asstDiv.children.length).toBe(1);
  });
});
