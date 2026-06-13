// Centralized shared state — replaces window/globalThis globals
// Each piece of state has explicit get/set with no global leakage

let _sessionId = null;
let _defaultModel = 'big-pickle';
let _debugVisible = false;
let _viewGeneration = 0;

export const SharedState = {
  getSessionId: () => _sessionId,
  setSessionId: (sid) => { _sessionId = sid; },

  getDefaultModel: () => _defaultModel,
  setDefaultModel: (m) => { _defaultModel = m; },

  isDebugVisible: () => _debugVisible,
  setDebugVisible: (v) => { _debugVisible = v; },

  nextViewGeneration: () => ++_viewGeneration,
  getViewGeneration: () => _viewGeneration,
};
