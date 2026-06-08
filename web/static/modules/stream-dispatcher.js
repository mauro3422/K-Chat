/* eslint-disable no-redeclare, no-unused-vars */
var KairosStream = (function() {
  var dispatcher = {
    listeners: {},
    on: function(event, cb) {
      if (!this.listeners[event]) this.listeners[event] = [];
      this.listeners[event].push(cb);
    },
    emit: function(event, data, state) {
      var list = this.listeners[event] || [];
      for (var i = 0; i < list.length; i++) {
        try { list[i](data, state); }
        catch (e) { console.error('Error in listener for ' + event + ':', e); }
      }
    }
  };

  dispatcher.on('reasoning', function(token) { logStream('reasoning', token); });
  dispatcher.on('content', function(token) { logStream('content', token); });
  dispatcher.on('tool_call', function(dataStr) { logStream('tool_call', dataStr); });
  dispatcher.on('error', function(errorData) {
    logStream('error', JSON.stringify(errorData));
    logUI('stream_backend_error', errorData.type + ': ' + errorData.message);
    KairosUtils.showToast(errorData.message, 'error');
  });

  return dispatcher;
})();
