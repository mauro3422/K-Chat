export interface SSEStreamReasoning {
  session_id: string;
  text: string;
}

export interface SSEStreamContent {
  session_id: string;
  text: string;
}

export interface SSEStreamTool {
  session_id: string;
  tool_name: string;
  tool_id: string;
  status: string;
}

export interface SSEStreamMemory {
  session_id: string;
  text: string;
}

export interface SSEStreamError {
  session_id: string;
  error: string;
}

export interface SSEStreamNotification {
  session_id: string;
  type: 'info' | 'warning' | 'error' | 'success';
  message: string;
  duration?: number;
}

export interface SSENewMessage {
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  phases?: string;
  ts: number;
}

export interface SSESessionDeleted {
  session_id: string;
}

export interface SSESessionRenamed {
  session_id: string;
  name: string;
}

export interface SSEMessageDeleted {
  session_id: string;
  message_id: number;
}

export interface SSEMemoryWriteQueued {
  key: string;
  value: string;
  reason: string;
  node_id: string;
  requested_at: number;
}

export interface SSEMemoryWriteCompleted {
  key: string;
  value: string;
  node_id: string;
  result: string;
}

export type SSEEvent =
  | { type: 'ping'; data?: undefined }
  | { type: 'stream:reasoning'; data: SSEStreamReasoning }
  | { type: 'stream:content'; data: SSEStreamContent }
  | { type: 'stream:tool'; data: SSEStreamTool }
  | { type: 'stream:memory'; data: SSEStreamMemory }
  | { type: 'stream:error'; data: SSEStreamError }
  | { type: 'stream:notification'; data: SSEStreamNotification }
  | { type: 'new_message'; data: SSENewMessage }
  | { type: 'session_renamed'; data: SSESessionRenamed }
  | { type: 'session_deleted'; data: SSESessionDeleted }
  | { type: 'message_deleted'; data: SSEMessageDeleted }
  | { type: 'memory_write_queued'; data: SSEMemoryWriteQueued }
  | { type: 'memory_write_completed'; data: SSEMemoryWriteCompleted };
