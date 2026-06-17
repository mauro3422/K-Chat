// Unified API client. Single source of truth for all backend communication.
// Every fetch() call in the frontend should go through this module.

import { SessionContext } from './session-context.js';

export const ApiClient = {
  // Chat
  chatStream(sessionId, message, model, controller) {
    var formData = new FormData();
    formData.append('message', message);
    return fetch('/chat/' + sessionId + '?model=' + encodeURIComponent(model), {
      method: 'POST',
      body: formData,
      signal: controller.signal
    });
  },

  chatStreamWithFiles(sessionId, message, model, controller, files) {
    var formData = new FormData();
    formData.append('message', message);
    for (var i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }
    return fetch('/chat/' + sessionId + '?model=' + encodeURIComponent(model), {
      method: 'POST',
      body: formData,
      signal: controller.signal
    });
  },

  // Sessions
  sidebar() {
    var urlBuilder = SessionContext.createSessionUrlBuilder();
    return fetch(urlBuilder.sidebar(), { cache: 'no-store' }).then(function(r) { return r.text(); });
  },

  loadMessages(sessionId) {
    return fetch('/sessions/' + sessionId + '/messages');
  },

  renameSession(sessionId, name) {
    return fetch('/sessions/' + sessionId + '/rename', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: name})
    });
  },

  deleteSession(sessionId) {
    return fetch('/sessions/' + sessionId + '/delete', { method: 'POST' });
  },

  favoriteSession(sessionId, favorite) {
    return fetch('/sessions/' + sessionId + '/favorite', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({favorite: favorite})
    });
  },

  // Widgets
  saveWidgetState(sessionId, widgetId, state) {
    return fetch('/sessions/' + sessionId + '/widgets/' + widgetId + '/state', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ state: state })
    });
  },

  loadWidgetStates(sessionId) {
    return fetch('/sessions/' + sessionId + '/widgets/states');
  },

  loadWidgetCode(sessionId, widgetId) {
    return fetch('/sessions/' + sessionId + '/widgets/' + widgetId + '/code');
  },

  saveWidgetCode(sessionId, widgetId, code, description) {
    return fetch('/sessions/' + sessionId + '/widgets/' + widgetId + '/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ code: code, description: description })
    });
  },

  loadWidgetVersions(sessionId, widgetId) {
    return fetch('/sessions/' + sessionId + '/widgets/' + widgetId + '/versions');
  },

  loadWidgetVersionCode(sessionId, widgetId, version) {
    return fetch('/sessions/' + sessionId + '/widgets/' + widgetId + '/versions/' + version + '/code');
  },

  // Debug
  loadDebugInfo(sessionId) {
    return fetch('/sessions/' + sessionId + '/debug');
  },

  loadBackendLogs() {
    return fetch('/debug/backend-logs');
  },



  // Logs
  sendClientLogs(entries) {
    return fetch('/api/logs/client', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(entries),
      keepalive: true
    });
  },

  deleteMessage(sessionId, messageId) {
    return fetch('/chat/' + sessionId + '/messages/' + messageId, {
      method: 'DELETE'
    });
  },

  // ASR (Speech-to-text)
  transcribeAudio(audioBlob, sessionId) {
    var formData = new FormData();
    formData.append('audio', audioBlob);
    if (sessionId) formData.append('session_id', sessionId);
    var url = '/api/asr/transcribe';
    if (sessionId) url += '?session_id=' + encodeURIComponent(sessionId);
    return fetch(url, {
      method: 'POST',
      body: formData
    });
  }
};
