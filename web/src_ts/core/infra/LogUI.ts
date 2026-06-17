export type StreamLogEvent = {
  id: number;
  t: string;
  d: string;
  at: string;
};

export type UiLogEvent = {
  id: number;
  label: string;
  detail: string;
  at: string;
};

type StreamListener = (() => void) | null;
type UiListener = (() => void) | null;

let debugVisible = false;
const streamEvents: StreamLogEvent[] = [];
let streamEvId = 0;
const uiEvents: UiLogEvent[] = [];
let uiEvId = 0;

let streamListener: StreamListener = null;
let uiListener: UiListener = null;

export function registerStreamListener(cb: () => void): void {
  streamListener = cb;
}

export function registerUiListener(cb: () => void): void {
  uiListener = cb;
}

export function logStream(tipo: string, data: unknown): void {
  streamEvents.push({
    id: ++streamEvId,
    t: tipo,
    d: typeof data === 'string' ? data : JSON.stringify(data),
    at: new Date().toISOString().slice(11, 23),
  });
  if (streamEvents.length > 500) streamEvents.shift();
  if (debugVisible && streamListener) {
    try {
      streamListener();
    } catch (error) {
      console.error(error);
    }
  }
}

export function logUI(label: string, detail: unknown): void {
  uiEvents.push({
    id: ++uiEvId,
    label,
    detail: String(detail || '').substring(0, 160),
    at: new Date().toISOString().slice(11, 23),
  });
  if (uiEvents.length > 60) uiEvents.shift();
  if (debugVisible && uiListener) {
    try {
      uiListener();
    } catch (error) {
      console.error(error);
    }
  }
}

export function setDebugVisible(v: boolean): void {
  debugVisible = v;
}

export function getStreamEvents(): StreamLogEvent[] {
  return streamEvents;
}

export function getUIEvents(): UiLogEvent[] {
  return uiEvents;
}

