// DomContracts — Single source of truth for shared CSS class names
// No module should hardcode these strings. Import from here.

var C = {};

// Messages
C.MSG_BODY = 'msg-body';
C.MD_CONTENT = 'md-content';
C.MSG_TEXT_SEGMENT = 'msg-text-segment';
C.MSG_BODY_MD = function() { return C.MSG_BODY + ' ' + C.MD_CONTENT; };

// Reasoning
C.REASONING = 'reasoning';
C.RT = 'rt';

// Tool Calls
C.TOOL_CALLS = 'tool-calls';
C.TC_ITEM = 'tc-item';
C.TC_ITEM_CALLING = 'tc-item calling';
C.TC_ITEM_OK = 'tc-item ok';
C.TC_ITEM_ERROR = 'tc-item error';

// Errors
C.ERROR_CARD = 'error-card';

// Widgets
C.WIDGET_CONTAINER = 'interactive-widget-container';

export default C;
