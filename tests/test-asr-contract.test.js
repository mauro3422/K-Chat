import { describe, expect, test, vi, beforeEach } from 'vitest';
import './setup.js';
import {
  appendAsrTelemetry,
  getAsrTelemetryBuffer,
  getAsrVisibleText,
  getAsrTransportConfig,
  setAsrTransportConfig,
  setAsrVisibleText,
} from '../web/static/modules/asr/contract.js';

describe('ASR contract', () => {
  beforeEach(() => {
    global.window.__ASR_TELEMETRY__ = [];
    global.window.__ASR_CURRENT_TEXT__ = '';
    global.window.__ASR_CONFIG__ = null;
    global.window._lastEvent = null;
  });

  test('appendAsrTelemetry stores bounded telemetry and emits an event', () => {
    const result = appendAsrTelemetry({ transport: 'ws', success: true });
    expect(result).toHaveLength(1);
    expect(result[0].transport).toBe('ws');
    expect(getAsrTelemetryBuffer()).toHaveLength(1);
    expect(global.window._lastEvent.detail.transport).toBe('ws');
  });

  test('setAsrVisibleText stores visible text and getAsrVisibleText trims it', () => {
    setAsrVisibleText('  hola mundo  ');
    expect(getAsrVisibleText()).toBe('hola mundo');
    expect(global.window._lastEvent.detail).toBe('  hola mundo  ');
  });

  test('transport config defaults to websocket and can be overridden', () => {
    expect(getAsrTransportConfig().transport).toBe('websocket');
    setAsrTransportConfig({ transport: 'websocket', mode: 'strict' });
    expect(getAsrTransportConfig()).toEqual({ transport: 'websocket', mode: 'strict' });
  });
});

