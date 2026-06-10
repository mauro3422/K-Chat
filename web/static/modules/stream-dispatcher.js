/* eslint-disable no-redeclare, no-unused-vars */

const listeners = {};

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

on('reasoning', function(token) { logStream('reasoning', token); });
on('content', function(token) { logStream('content', token); });
on('tool_call', function(dataStr) { logStream('tool_call', dataStr); });
on('error', function(errorData) {
  logStream('error', JSON.stringify(errorData));
  logUI('stream_backend_error', errorData.type + ': ' + errorData.message);
  KairosUtils.showToast(errorData.message, 'error');
});

export const KairosStream = { on, emit, off };
window.KairosStream = KairosStream;
