import { IWidgetApi } from '../../types/api';

export interface IWidgetStateManager {
  getState(id: string): string | null;
  setState(id: string, state: string): void;
  loadFromJSON(json: Record<string, string>): void;
  toJSON(): Record<string, string>;
  clear(): void;
  has(id: string): boolean;
  delete(id: string): void;
}

export class WidgetStateManager implements IWidgetStateManager {
  private store = new Map<string, string>();
  private apiClient?: IWidgetApi;
  private sessionId?: string;

  constructor(apiClient?: IWidgetApi, sessionId?: string) {
    this.apiClient = apiClient;
    this.sessionId = sessionId;
  }

  getState(id: string): string | null {
    return this.store.get(id) ?? null;
  }

  setState(id: string, state: string): void {
    this.store.set(id, state);
    if (this.apiClient && this.sessionId) {
      this.apiClient.saveWidgetState(this.sessionId, id, state)
        .catch((err) => console.error('Widget state save failed:', err));
    }
  }

  loadFromJSON(json: Record<string, string>): void {
    if (!json || typeof json !== 'object') return;
    for (const [k, v] of Object.entries(json)) {
      this.store.set(k, v);
    }
  }

  toJSON(): Record<string, string> {
    const obj: Record<string, string> = {};
    for (const [k, v] of this.store) {
      obj[k] = v;
    }
    return obj;
  }

  clear(): void {
    this.store.clear();
  }

  has(id: string): boolean {
    return this.store.has(id);
  }

  delete(id: string): void {
    this.store.delete(id);
  }

  async persist(widgetId?: string): Promise<void> {
    if (!this.apiClient || !this.sessionId) return;
    if (widgetId) {
      const state = this.store.get(widgetId);
      if (state !== undefined) {
        await this.apiClient.saveWidgetState(this.sessionId, widgetId, state);
      }
    } else {
      const promises: Promise<Response>[] = [];
      for (const [id, state] of this.store) {
        promises.push(this.apiClient.saveWidgetState(this.sessionId, id, state));
      }
      await Promise.allSettled(promises);
    }
  }
}
