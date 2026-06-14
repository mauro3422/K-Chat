import { StreamDispatcher } from './stream-dispatcher.js';
import { parseStreamEvent } from './stream-contract.js';
import { logUI } from './log-ui.js';
import { ApiClient } from './api-client.js';

export function executeStreamFetch(params) {
  var sessionId = params.sessionId;
  var defaultModel = params.defaultModel;
  var text = params.text;
  var controller = params.controller;
  var errorHandler = params.errorHandler;
  var context = params.context || params.state;
  var onChunk = params.onChunk;

  var buf = '';
  var hasContent = false;
  var tokenCount = 0;

  return ApiClient.chatStream(sessionId, text, defaultModel, controller).then(function(resp) {
    if (resp.status === 401) {
      errorHandler.handler('error', { type: 'auth', message: 'Error de autenticación. Verifica tu API key.' });
      throw new Error('HTTP ' + resp.status);
    } else if (resp.status === 429) {
      errorHandler.handler('error', { type: 'rate_limit', message: 'Límite de tasa alcanzado. Espera un momento.' });
      throw new Error('HTTP ' + resp.status);
    } else if (resp.status >= 500) {
      errorHandler.handler('error', { type: 'server', message: 'Error del servidor (' + resp.status + ')' });
      throw new Error('HTTP ' + resp.status);
    }

    var reader = resp.body.getReader();
    var decoder = new TextDecoder();

    function readLoop() {
      return reader.read().then(function(r) {
        if (r.done) {
          buf += decoder.decode();
          if (buf.trim()) {
            var lastMsg = parseStreamEvent(buf);
            if (!lastMsg) {
              logUI('json_parse_error', buf.substring(0, 80));
            } else {
              StreamDispatcher.emit(lastMsg.t, lastMsg.d, context);
            }
          }
          logUI('stream_complete', 'tokens=' + tokenCount + ' hasContent=' + hasContent);
          return { hasContent: hasContent, tokenCount: tokenCount };
        }

        if (onChunk) onChunk();
        buf += decoder.decode(r.value, {stream: true});
        var lines = buf.split('\n');
        buf = lines.pop();

        for (var i = 0; i < lines.length; i++) {
          var line = lines[i];
          if (!line.trim()) continue;
          var msg = parseStreamEvent(line);
          if (!msg) { logUI('json_parse_error', line.substring(0, 80)); continue; }

          var isFirstToken = context.isFirstToken ? context.isFirstToken() : context.firstToken;
          if (isFirstToken) {
            var bodyDivs = context.getBodyDivs ? context.getBodyDivs() : context.bodyDivs;
            bodyDivs[0].textContent = '';
            if (context.clearFirstToken) context.clearFirstToken();
            else context.firstToken = false;
            logUI('pensando_cleared', '' + msg.t);
          }

          if (msg.t === 'heartbeat') {
            if (onChunk) onChunk();
            continue;
          }

          if (msg.t === 'content' && msg.d && msg.d.trim()) {
            hasContent = true;
            tokenCount++;
          }

          StreamDispatcher.emit(msg.t, msg.d, context);
        }

        return readLoop();
      });
    }

    return readLoop();
  })
  .catch(function(err) {
    var isAbort = err && (err.name === 'AbortError' || String(err.message || '').toLowerCase().indexOf('aborted') >= 0);
    if (!isAbort) {
      console.error('Chat request failed:', err);
      if (errorHandler) errorHandler.handler('error', {type: 'network', message: 'Connection failed'});
    }
    throw err;
  });
}
