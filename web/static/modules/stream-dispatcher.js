/* eslint-disable no-redeclare, no-unused-vars */

import { Utils } from './utils.js';
import { logUI, logStream } from './log-ui.js';

const listeners = {};
const ALL_EVENTS = ['reasoning', 'content', 'tool_call', 'error'];

function on(event, cb) {
  if (!listeners[event]) listeners[event] = [];
  listeners[event].push(cb);
}

function emit(event, data, state) {
  var list = listeners[event] || [];
  for (var i = 0; i < list.length; i++) {
    try { list[i](data, state); }
    catch (e) { console.error('Error in listener for ' + event + ':', e); }
  }
}

function off(event, cb) {
  if (!listeners[event]) return;
  listeners[event] = listeners[event].filter(fn => fn !== cb);
}

function removeAllListeners(event) {
  if (event) {
    listeners[event] = [];
  } else {
    ALL_EVENTS.forEach(function(ev) { listeners[ev] = []; });
  }
}

// Logging listeners — registrados una vez, no se limpian
on('reasoning', function(token) { logStream('reasoning', token); });
on('content', function(token) { logStream('content', token); });
on('tool_call', function(dataStr) { logStream('tool_call', dataStr); });
on('error', function(errorData) {
  logStream('error', JSON.stringify(errorData));
  logUI('stream_backend_error', errorData.type + ': ' + errorData.message);
  Utils.showToast(errorData.message, 'error');
});

export const StreamDispatcher = { on, emit, off, removeAllListeners, ALL_EVENTS };
