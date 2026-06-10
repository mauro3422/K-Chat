// main.js — ES modules entry point for K-Chat frontend
// This file imports all frontend modules and initializes them.
// It's designed to work with Vite for development (HMR) and production (bundling).

// === Utilities ===
import { KairosUtils } from './modules/utils.js';

// === Widget System ===
import { KairosWidgets } from './modules/widgets/core.js';
import { createToolbarButton } from './modules/widgets/ui-helpers.js';
import { buildIframeSrc, createIframe } from './modules/widgets/iframe-builder.js';
import { createToolbar } from './modules/widgets/toolbar-core.js';
import { openEditor } from './modules/widgets/toolbar-editor.js';
import { toggleHistoryList } from './modules/widgets/toolbar-history.js';
import './modules/widgets/iframe.js';
import './modules/widgets/messaging.js';
import './modules/widgets/index.js';

// === Markdown ===
import { KairosMarkdown } from './modules/markdown-renderer.js';

// === Stream System ===
import { KairosStream } from './modules/stream-dispatcher.js';
import './modules/reasoning-handler.js';
import './modules/content-handler.js';
import './modules/tool-call-renderer.js';
import './modules/stream-renderer.js';
import { RetryHandler } from './modules/retry-handler.js';
import { StreamErrorHandler } from './modules/stream-error-handler.js';

// === Chat Form ===
import { KairosForm } from './modules/chat-form.js';
import { StreamOrchestrator } from './modules/stream-orchestrator.js';

// === Debug ===
import { KairosDebug } from '../debug.js';

// === Session ===
import { KairosSession } from '../session.js';

// === Stream Loading ===
import '../chat-stream.js';

// Expose to window for backwards compatibility and HTML onclick handlers
window.KairosUtils = KairosUtils;
window.KairosWidgets = KairosWidgets;
window.KairosMarkdown = KairosMarkdown;
window.KairosStream = KairosStream;
window.KairosForm = KairosForm;
window.KairosSession = KairosSession;
window.StreamOrchestrator = StreamOrchestrator;
window.RetryHandler = RetryHandler;
window.StreamErrorHandler = StreamErrorHandler;

// Widget system augmenting pattern (backwards compatible)
window.createToolbarButton = createToolbarButton;
window.buildIframeSrc = buildIframeSrc;
window.createIframe = createIframe;
window.createToolbar = createToolbar;
window.openEditor = openEditor;
window.toggleHistoryList = toggleHistoryList;

console.log('Kairos modules loaded (ES modules)');
