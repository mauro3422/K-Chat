export interface PhaseData {
  memory?: string;
  reasoning?: string;
  content?: string;
  retry?: {
    attempt: number;
    max_retries: number;
    error_type?: string;
    error_message?: string;
    status?: 'waiting' | 'active' | 'completed' | 'failed';
  };
}

export interface MessageData {
  id?: string | number;
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  ts?: number | string;
  phases?: PhaseData[];
  matched_tools?: Array<{ tool_name: string; status: 'ok' | 'error' | string; turn?: number }>;
}
