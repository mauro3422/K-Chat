export const STREAM_EVENT_TYPES = {
  HEARTBEAT: 'heartbeat',
  CONTENT: 'content',
  REASONING: 'reasoning',
  TOOL_CALL: 'tool_call',
  ERROR: 'error',
  MEMORY: 'memory'
};

export const STREAM_EVENT_VALUES = Object.values(STREAM_EVENT_TYPES);

export function isStreamEventType(type) {
  return STREAM_EVENT_VALUES.indexOf(type) >= 0;
}

export function parseStreamEvent(raw) {
  if (!raw) return null;
  var msg = raw;
  if (typeof raw === 'string') {
    try {
      msg = JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }
  if (!msg || typeof msg !== 'object') return null;
  if (typeof msg.t !== 'string' || !isStreamEventType(msg.t)) return null;
  return { t: msg.t, d: msg.d };
}

export function serializeStreamEvent(type, data) {
  if (!isStreamEventType(type)) {
    throw new Error('Unsupported stream event type: ' + type);
  }
  return JSON.stringify({ t: type, d: data }) + '\n';
}
