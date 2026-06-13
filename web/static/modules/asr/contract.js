export const ASR_TELEMETRY_KEY = '__ASR_TELEMETRY__';
export const ASR_TEXT_KEY = '__ASR_CURRENT_TEXT__';
export const ASR_CONFIG_KEY = '__ASR_CONFIG__';
export const ASR_EVENT_TELEMETRY = 'asr:telemetry';
export const ASR_EVENT_TEXT = 'asr:text';

function getWindow() {
  return typeof window !== 'undefined' ? window : null;
}

export function getAsrTelemetryBuffer() {
  const win = getWindow();
  if (!win) return [];
  if (!win[ASR_TELEMETRY_KEY]) {
    win[ASR_TELEMETRY_KEY] = [];
  }
  return win[ASR_TELEMETRY_KEY];
}

export function appendAsrTelemetry(event) {
  const buffer = getAsrTelemetryBuffer();
  buffer.push({
    at: new Date().toISOString(),
    ...event,
  });
  if (buffer.length > 100) {
    buffer.splice(0, buffer.length - 100);
  }
  const win = getWindow();
  if (win) {
    if (typeof CustomEvent !== 'undefined') {
      win.dispatchEvent(new CustomEvent(ASR_EVENT_TELEMETRY, { detail: event }));
    }
  }
  return buffer;
}

export function setAsrVisibleText(text) {
  const win = getWindow();
  if (!win) return '';
  win[ASR_TEXT_KEY] = text || '';
  if (typeof CustomEvent !== 'undefined') {
    win.dispatchEvent(new CustomEvent(ASR_EVENT_TEXT, { detail: win[ASR_TEXT_KEY] }));
  }
  return win[ASR_TEXT_KEY];
}

export function getAsrVisibleText() {
  const win = getWindow();
  if (!win) return '';
  return (win[ASR_TEXT_KEY] || '').trim();
}

export function getAsrTransportConfig() {
  const win = getWindow();
  if (!win) {
    return { transport: 'websocket' };
  }
  return win[ASR_CONFIG_KEY] || { transport: 'websocket' };
}

export function setAsrTransportConfig(config) {
  const win = getWindow();
  if (!win) return;
  win[ASR_CONFIG_KEY] = {
    transport: 'websocket',
    ...config,
  };
}

export function hasAsrTelemetry() {
  return getAsrTelemetryBuffer().length > 0;
}
