export interface SessionUrlBuilder {
  widgetCode(key: string): string;
  widgetState(key: string): string;
  widgetSave(key: string): string;
  widgetVersions(key: string): string;
  versionCode(key: string, v: string | number): string;
  debug(): string;
  sidebar(): string;
  chat(model: string): string;
  messages(): string;
}

export interface ISessionContext {
  getSessionId(): string | null;
  isInitialized(): boolean;
  setSessionId(sid: string): string | null;
  createSessionUrlBuilder(): SessionUrlBuilder;
  reset(): void;
}

export interface IChatApi {
  chatStream(sessionId: string, message: string, model: string, controller: AbortController): Promise<Response>;
  chatStreamWithFiles(sessionId: string, message: string, model: string, controller: AbortController, files: File[]): Promise<Response>;
  loadMessages(sessionId: string): Promise<Response>;
  deleteMessage(sessionId: string, messageId: string): Promise<Response>;
}

export interface ISessionApi {
  getSessions(): Promise<Response>;
  createSession(): Promise<Response>;
  getSessionMessages(sessionId: string): Promise<Response>;
  renameSession(sessionId: string, name: string): Promise<Response>;
  deleteSession(sessionId: string): Promise<Response>;
  sidebar(currentSessionId?: string): Promise<Response>;
  sessionDebug(sessionId: string): Promise<Response>;
}

export interface IWidgetApi {
  saveWidgetState(sessionId: string, widgetId: string, state: string): Promise<Response>;
  loadWidgetStates(sessionId: string): Promise<Response>;
  loadWidgetCode(sessionId: string, widgetId: string): Promise<Response>;
  saveWidgetCode(sessionId: string, widgetId: string, code: string, description: string): Promise<Response>;
  loadWidgetVersions(sessionId: string, widgetId: string): Promise<Response>;
  loadWidgetVersionCode(sessionId: string, widgetId: string, version: number): Promise<Response>;
}

export interface ClientLogEntry {
  t: string;
  l: string;
  m: string;
  msg: string;
  d: unknown;
}

export interface IDebugApi {
  loadDebugInfo(sessionId: string): Promise<Response>;
  loadBackendLogs(): Promise<Response>;
  loadSystemLogs(): Promise<Response>;
  sendClientLogs(entries: ClientLogEntry[]): Promise<Response>;
}

export interface IApiClient extends IChatApi, ISessionApi, IWidgetApi, IDebugApi {}
