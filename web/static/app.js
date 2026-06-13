import { SessionContext } from './modules/session-context.js';
import './modules/reasoning-handler.js';
import './modules/content-handler.js';
import './modules/tool-call-renderer.js';
import './modules/asr-mic.js';
import { initSessionPage } from './modules/session-page.js';
import { KairosForm } from './modules/chat-form.js';
import { KairosDebugPanel } from './modules/debug-panel.js';

SessionContext.init(window.__SESSION_ID);
initSessionPage();
KairosDebugPanel.bindDebugControls();
KairosForm.init();
