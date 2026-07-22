import { IChatApi, ISessionApi, IWidgetApi, IDebugApi, IApiClient, ClientLogEntry, RetryRequest } from '../types/api';

export class ApiClient implements IChatApi, ISessionApi, IWidgetApi, IDebugApi {
  private baseUrl: string;

  constructor(baseUrl: string = '') {
    this.baseUrl = baseUrl;
  }

  chatStream(sessionId: string, message: string, model: string, controller: AbortController, retry?: RetryRequest): Promise<Response> {
    const formData = new FormData();
    formData.append('message', message);
    this.appendRetry(formData, retry);
    return fetch(`${this.baseUrl}/chat/${sessionId}?model=${encodeURIComponent(model)}`, {
      method: 'POST',
      body: formData,
      signal: controller.signal
    });
  }

  chatStreamWithFiles(sessionId: string, message: string, model: string, controller: AbortController, files: File[], retry?: RetryRequest): Promise<Response> {
    const formData = new FormData();
    formData.append('message', message);
    this.appendRetry(formData, retry);
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }
    return fetch(`${this.baseUrl}/chat/${sessionId}?model=${encodeURIComponent(model)}`, {
      method: 'POST',
      body: formData,
      signal: controller.signal
    });
  }

  getSessions(): Promise<Response> {
    return fetch(`${this.baseUrl}/sessions`);
  }

  health(): Promise<Response> {
    return fetch(`${this.baseUrl}/health`, { cache: 'no-store' });
  }

  createSession(): Promise<Response> {
    return fetch(`${this.baseUrl}/sessions/create`, { method: 'POST' });
  }

  getSessionMessages(sessionId: string): Promise<Response> {
    return fetch(`${this.baseUrl}/sessions/${sessionId}/messages`);
  }

  sidebar(currentSessionId?: string): Promise<Response> {
    let url = `${this.baseUrl}/sidebar`;
    if (currentSessionId) {
      url += `?current=${encodeURIComponent(currentSessionId)}`;
    }
    return fetch(url, { cache: 'no-store' });
  }

  sessionDebug(sessionId: string): Promise<Response> {
    return fetch(`${this.baseUrl}/sessions/${sessionId}/debug`);
  }

  loadMessages(sessionId: string): Promise<Response> {
    return fetch(`${this.baseUrl}/sessions/${sessionId}/messages`);
  }

  deleteMessage(sessionId: string, messageId: string): Promise<Response> {
    return fetch(`${this.baseUrl}/chat/${sessionId}/messages/${messageId}`, {
      method: 'DELETE'
    });
  }

  renameSession(sessionId: string, name: string): Promise<Response> {
    return fetch(`${this.baseUrl}/sessions/${sessionId}/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });
  }

  deleteSession(sessionId: string): Promise<Response> {
    return fetch(`${this.baseUrl}/sessions/${sessionId}/delete`, { method: 'POST' });
  }

  favoriteSession(sessionId: string, favorite: boolean): Promise<Response> {
    return fetch(`${this.baseUrl}/sessions/${sessionId}/favorite`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ favorite })
    });
  }

  private appendRetry(formData: FormData, retry?: RetryRequest): void {
    if (!retry?.resume) return;
    formData.append('resume', 'true');
    formData.append('retry_error_type', retry.errorType || 'unknown');
    formData.append('retry_error_message', retry.errorMessage || '');
    formData.append('retry_count', String(retry.retryCount || 1));
  }

  saveWidgetState(sessionId: string, widgetId: string, state: string): Promise<Response> {
    return fetch(`${this.baseUrl}/sessions/${sessionId}/widgets/${widgetId}/state`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state })
    });
  }

  loadWidgetStates(sessionId: string): Promise<Response> {
    return fetch(`${this.baseUrl}/sessions/${sessionId}/widgets/states`);
  }

  loadWidgetCode(sessionId: string, widgetId: string): Promise<Response> {
    return fetch(`${this.baseUrl}/sessions/${sessionId}/widgets/${widgetId}/code`);
  }

  saveWidgetCode(sessionId: string, widgetId: string, code: string, description: string): Promise<Response> {
    return fetch(`${this.baseUrl}/sessions/${sessionId}/widgets/${widgetId}/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, description })
    });
  }

  loadWidgetVersions(sessionId: string, widgetId: string): Promise<Response> {
    return fetch(`${this.baseUrl}/sessions/${sessionId}/widgets/${widgetId}/versions`);
  }

  loadWidgetVersionCode(sessionId: string, widgetId: string, version: number): Promise<Response> {
    return fetch(`${this.baseUrl}/sessions/${sessionId}/widgets/${widgetId}/versions/${version}/code`);
  }

  loadDebugInfo(sessionId: string): Promise<Response> {
    return fetch(`${this.baseUrl}/sessions/${sessionId}/debug`);
  }

  loadBackendLogs(): Promise<Response> {
    return fetch(`${this.baseUrl}/debug/backend-logs`);
  }

  loadSystemLogs(): Promise<Response> {
    return fetch(`${this.baseUrl}/api/logs/tail?source=all&lines=200`, { cache: 'no-store' });
  }

  syncStatus(): Promise<Response> {
    // Browser-safe aggregate. The direct node endpoint is reserved for
    // signed node-to-node traffic and correctly rejects browser requests.
    return fetch(`${this.baseUrl}/api/diagnostics`, { cache: 'no-store' });
  }

  memoryDiagnostics(keyPattern: string = ''): Promise<Response> {
    const query = keyPattern ? `?key_pattern=${encodeURIComponent(keyPattern)}` : '';
    // Use the same-origin diagnostics facade; it signs peer requests on the
    // server without exposing the LAN shared secret to the browser.
    return fetch(`${this.baseUrl}/api/diagnostics${query}`, { cache: 'no-store' });
  }

  sendClientLogs(entries: ClientLogEntry[]): Promise<Response> {
    return fetch(`${this.baseUrl}/api/logs/client`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(entries)
    });
  }

  transcribeAudio(audioBlob: Blob, sessionId?: string): Promise<Response> {
    const formData = new FormData();
    formData.append('audio', audioBlob);
    if (sessionId) formData.append('session_id', sessionId);
    let url = `${this.baseUrl}/api/asr/transcribe`;
    if (sessionId) url += `?session_id=${encodeURIComponent(sessionId)}`;
    return fetch(url, {
      method: 'POST',
      body: formData
    });
  }
}
