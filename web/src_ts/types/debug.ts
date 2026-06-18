export interface IDebugManager {
  init(): void;
  logStream(type: string, detail: string): void;
  logUI(label: string, detail: string): void;
  logWidget(detail: string): void;
  setActiveMessage(el: HTMLElement | null, state: Record<string, unknown> | null): void;
  refresh(): void;
  getAllText(): string;
  loadDebugInfo(sessionId: string): Promise<void>;
  loadBackendLogs(): Promise<void>;
  setSessionId(sessionId: string): void;
}
