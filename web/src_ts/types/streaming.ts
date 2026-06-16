/** NDJSON event types matching the production stream-contract.js */
export const STREAM_EVENT_TYPES = {
  HEARTBEAT: 'heartbeat',
  CONTENT: 'content',
  REASONING: 'reasoning',
  TOOL_CALL: 'tool_call',
  ERROR: 'error',
  MEMORY: 'memory',
} as const;

export type StreamEventType = (typeof STREAM_EVENT_TYPES)[keyof typeof STREAM_EVENT_TYPES];

/** Raw NDJSON line: { t: type, d: data } */
export interface StreamEvent {
  t: StreamEventType;
  d: string;
}

/** Parsed tool_call payload */
export interface ToolCallPayload {
  status: 'calling' | 'ok' | 'error';
  name: string;
  id?: string;
}

/** A detected widget marker inside streamed content */
export interface WidgetMarker {
  type: 'block' | 'tag';
  key?: string;
  code?: string;
  startPos: number;
  endPos: number;
}

/** Configuration for how the simulator should behave */
export interface SimulatorConfig {
  /** Keywords to influence response type (default: from user message) */
  intent?: 'default' | 'research' | 'widget' | 'code' | 'error' | 'rich_markdown';
  /** Force inclusion of a widget in the response */
  includeWidget?: boolean;
  /** Number of tool calls to simulate (0-3) */
  toolCount?: number;
  /** Whether to simulate a memory phase */
  includeMemory?: boolean;
  /** Simulated delay between tokens in ms */
  tokenDelay?: number;
}
