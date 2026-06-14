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
setAsrTransportConfig({ transport: 'websocket' });
startMessageHandler({ eventTarget: window, locationOrigin: window.location.origin, Observer: window.IntersectionObserver });
initSessionPage({ nav });
DebugPanel.bindDebugControls();
ChatForm.init({ nav });
