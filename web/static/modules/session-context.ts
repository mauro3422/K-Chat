let currentSessionId: string | null = null;
let initialized = false;

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

export const SessionContext: ISessionContext = {
  init(sid: string): void {
    currentSessionId = sid;
    initialized = true;
  },

  getSessionId(): string | null {
    return currentSessionId;
  },

  isInitialized(): boolean {
    return initialized;
  },

  setSessionId(sid: string): string | null {
    const prev = currentSessionId;
    currentSessionId = sid;
    return prev;
  },

  createSessionUrlBuilder(): SessionUrlBuilder {
    const sid = currentSessionId;
    return {
      widgetCode: (key: string) => `/sessions/${sid}/widgets/${encodeURIComponent(key)}/code`,
      widgetState: (key: string) => `/sessions/${sid}/widgets/${encodeURIComponent(key)}/state`,
      widgetSave: (key: string) => `/sessions/${sid}/widgets/${encodeURIComponent(key)}/save`,
      widgetVersions: (key: string) => `/sessions/${sid}/widgets/${encodeURIComponent(key)}/versions`,
      versionCode: (key: string, v: string | number) => `/sessions/${sid}/widgets/${encodeURIComponent(key)}/versions/${v}/code`,
      debug: () => `/sessions/${sid}/debug`,
      sidebar: () => `/sidebar?current=${sid}`,
      chat: (model: string) => `/chat/${sid}?model=${encodeURIComponent(model)}`,
      messages: () => `/sessions/${sid}/messages`,
    };
  },

  reset(): void {
    currentSessionId = null;
    initialized = false;
  },
};

export default SessionContext;
