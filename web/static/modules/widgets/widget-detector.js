import { StreamDispatcher } from '../stream-dispatcher.js';

const stateMemory = new WeakMap();

function getPhase(state) {
  return Number.isInteger(state?._toolPhase) ? state._toolPhase : 0;
}

function getPhaseStore(state, phaseIdx) {
  let entry = stateMemory.get(state);
  if (!entry) {
    entry = { buffers: [], emitted: [] };
    stateMemory.set(state, entry);
  }
  if (!entry.buffers[phaseIdx]) entry.buffers[phaseIdx] = '';
  if (!entry.emitted[phaseIdx]) entry.emitted[phaseIdx] = new Set();
  return entry;
}

function scanAndEmit(text, state) {
  if (!state || !Array.isArray(state.bodyDivs)) return;
  const phaseIdx = getPhase(state);
  const bodyDiv = state.bodyDivs[phaseIdx];
  if (!bodyDiv) return;

  const store = getPhaseStore(state, phaseIdx);
  store.buffers[phaseIdx] += String(text || '');
  const fullText = store.buffers[phaseIdx];
  const seen = store.emitted[phaseIdx];

  const blockRe = /```html-widget(?:\s+([\w\-]+))?\s*\n([\s\S]*?)\n```/g;
  const tagRe = /\[Widget:?\s*([\w\-]+)\]/gi;
  let match;

  while ((match = blockRe.exec(fullText)) !== null) {
    const key = match[1] || null;
    const code = String(match[2] || '').trim();
    if (!code) continue;
    const sig = `block|${key || ''}|${code}`;
    if (seen.has(sig)) continue;
    seen.add(sig);
    StreamDispatcher.emit('widget:detected', { key, code, phaseIdx, bodyDiv });
  }

  while ((match = tagRe.exec(fullText)) !== null) {
    const key = match[1];
    const sig = `tag|${key}`;
    if (seen.has(sig)) continue;
    seen.add(sig);
    StreamDispatcher.emit('widget:detected', { key, code: '', phaseIdx, bodyDiv });
  }
}

StreamDispatcher.on('content', scanAndEmit);

export default {};
