import { SessionContext } from './modules/session-context.js';
import './modules/reasoning-handler.js';
import './modules/content-handler.js';
import './modules/tool-call-renderer.js';
import './modules/asr-mic.js';
import { initSessionPage } from './modules/session-page.js';
import { ChatForm } from './modules/chat-form.js';
import { DebugPanel } from './modules/debug-panel.js';
import { setAsrTransportConfig } from './modules/asr/contract.js';
import { startMessageHandler } from './modules/widgets/index.js';
import { setCurrentSessionId } from './modules/message-renderer.js';
// SSE client imported dynamically (not statically) to avoid breaking the page
const nav = {
  location: window.location,
  history: window.history,
  onDomReady(cb) {
    document.addEventListener('DOMContentLoaded', cb);
  },
  onPopState(cb) {
    window.addEventListener('popstate', cb);
  },
};

const appRoot = document.getElementById('app');
const sessionId = appRoot ? appRoot.dataset.sessionId : '';
SessionContext.init(sessionId);
setCurrentSessionId(sessionId);
setAsrTransportConfig({ transport: 'websocket' });
startMessageHandler({ eventTarget: window, locationOrigin: window.location.origin, Observer: window.IntersectionObserver });
initSessionPage({ nav });
DebugPanel.bindDebugControls();
ChatForm.init({ nav });

// SSE real-time updates (lazy connect, won't break page if fails)
import('./modules/sse-client.js').then(function(sse) {
  sse.setCurrentSessionId(sessionId);
  sse.connect();
}).catch(function(err) {
  console.warn('SSE unavailable (non-fatal):', err);
});
