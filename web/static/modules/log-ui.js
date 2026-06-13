/* global renderStreamLog, renderUILog */
/**
 * Log UI — Minimal event logger for debug panel.
 *
 * Extracted from debug.js to break circular import chain.
 * Pure functions, no dependencies on other modules.
 */

let debugVisible = false;
const streamEvents = [];
let streamEvId = 0;
const uiEvents = [];
let uiEvId = 0;

export function logStream(tipo, data) {
  streamEvents.push({id: ++streamEvId, t: tipo, d: typeof data === 'string' ? data : JSON.stringify(data), at: new Date().toISOString().slice(11,23)});
  if (streamEvents.length > 500) streamEvents.shift();
  if (debugVisible && typeof renderStreamLog === 'function') renderStreamLog();
}

export function logUI(label, detail) {
  uiEvents.push({id: ++uiEvId, label: label, detail: String(detail || '').substring(0, 160), at: new Date().toISOString().slice(11,23)});
  if (uiEvents.length > 60) uiEvents.shift();
  if (debugVisible && typeof renderUILog === 'function') renderUILog();
}

export function setDebugVisible(v) { debugVisible = v; }
export function getStreamEvents() { return streamEvents; }
export function getUIEvents() { return uiEvents; }
