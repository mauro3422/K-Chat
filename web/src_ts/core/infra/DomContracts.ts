export const C = {
  // Messages
  MSG_BODY: 'msg-body',
  MD_CONTENT: 'md-content',
  MSG_TEXT_SEGMENT: 'msg-text-segment',
  LIVE_MSG: 'live-msg',

  // Reasoning
  REASONING: 'reasoning',
  REASONING_MEMORIES: 'reasoning memories-phase',
  RT: 'rt',
  MEMORY_CONTENT: 'rt memory-content',

  // Tool Calls
  TOOL_CALLS: 'tool-calls',
  TC_ITEM: 'tc-item',
  TC_ITEM_CALLING: 'tc-item calling',
  TC_ITEM_OK: 'tc-item ok',
  TC_ITEM_ERROR: 'tc-item error',

  // Errors
  ERROR_CARD: 'error-card',
  RATE_LIMIT_CARD: 'rate-limit-card',
  ERROR_HEADER: 'error-header',
  ERROR_DETAIL: 'error-detail',
  ERROR_HINT: 'error-hint',
  RETRY_BTN: 'error-retry-btn',

  // Widgets
  WIDGET_CONTAINER: 'interactive-widget-container',
  WIDGET_IFRAME: 'widget-iframe',
  WIDGET_PLACEHOLDER: 'widget-placeholder',
  WIDGET_LOADING: 'widget-loading',
  WIDGET_ERROR: 'widget-error',
  WIDGET_TOOLBAR: 'widget-toolbar',

  // Misc
  MSG_LABEL: 'msg-label',
  MSG_TS: 'msg-ts',
  MSG_DELETE_BTN: 'msg-delete-btn',
  EMPTY_STATE: 'empty-state',
  STREAMING: 'streaming',
} as const;

export type CssClass = typeof C[keyof typeof C];
