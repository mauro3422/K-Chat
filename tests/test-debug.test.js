import { describe, test, expect, beforeEach } from 'vitest';
import './setup.js';

// Override debug-specific mocks
global.navigator.clipboard = { writeText: () => Promise.resolve() };
global.sessionId = 'debug-test-sid';
global.KairosUtils = { escHtml: (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') };
global.KairosWidgets = { debug: {}, log: () => {} };
global.fetch = () => Promise.resolve({ json: () => Promise.resolve({}) });

const { KairosDebugPanel } = await import('../web/static/modules/debug-panel.js');
KairosDebugPanel.bindDebugControls();

describe('KairosDebug', () => {
  test('logUI guarda evento en uiEvents', async () => {
    KairosDebugPanel.logUI('test-label', 'test-detail');
    const btn = { textContent: 'copy' };
    KairosDebugPanel.copyUILog(btn);
    await new Promise(r => setTimeout(r, 10));
    expect(btn.textContent).toBe('copiado');
  });

  test('logUI con label vacio no lanza error', () => {
    expect(() => KairosDebugPanel.logUI('', '')).not.toThrow();
  });

  test('logStream guarda evento en streamEvents', async () => {
    KairosDebugPanel.logStream('content', 'texto de prueba');
    const btn = { textContent: 'copy' };
    KairosDebugPanel.copyStreamLog(btn);
    await new Promise(r => setTimeout(r, 10));
    expect(btn.textContent).toBe('copiado');
  });

  test('logStream con data null no lanza error', () => {
    expect(() => KairosDebugPanel.logStream('error', null)).not.toThrow();
  });

  test('logStream con objeto data no lanza error', () => {
    expect(() => KairosDebugPanel.logStream('tool_call', { name: 'test', args: { x: 1 } })).not.toThrow();
  });

  test('toggleDebug abre panel primera vez', () => {
    const panelClasses = { _open: false, toggle(cls, val) { if (cls === 'open') this._open = val !== undefined ? val : !this._open; }, contains() { return this._open; } };
    const mainClasses = { _shifted: false, toggle(cls, val) { if (cls === 'shifted') this._shifted = val !== undefined ? val : !this._shifted; }, contains() { return this._shifted; } };
    global.document.getElementById = (id) => {
      if (id === 'debug-panel') return { classList: panelClasses };
      if (id === 'main') return { classList: mainClasses };
      return null;
    };
    KairosDebugPanel.toggleDebug();
    expect(panelClasses._open).toBe(true);
    expect(mainClasses._shifted).toBe(true);
  });

  test('toggleDebug cierra panel segunda vez', () => {
    const panelClasses = { _open: true, toggle(cls, val) { if (cls === 'open') this._open = val !== undefined ? val : !this._open; }, contains() { return this._open; } };
    const mainClasses = { _shifted: true, toggle(cls, val) { if (cls === 'shifted') this._shifted = val !== undefined ? val : !this._shifted; }, contains() { return this._shifted; } };
    global.document.getElementById = (id) => {
      if (id === 'debug-panel') return { classList: panelClasses };
      if (id === 'main') return { classList: mainClasses };
      return null;
    };
    KairosDebugPanel.toggleDebug();
    expect(panelClasses._open).toBe(false);
  });

  test('toggleDebug sin DOM no lanza error', () => {
    global.document.getElementById = () => null;
    expect(() => { KairosDebugPanel.toggleDebug(); KairosDebugPanel.toggleDebug(); }).not.toThrow();
  });

  test('toggleDebug es una función exportada', () => {
    expect(typeof KairosDebugPanel.toggleDebug).toBe('function');
  });

  test('copyText sin pre muestra []', () => {
    const btn = { textContent: 'copy', parentElement: { querySelector: () => null } };
    KairosDebugPanel.copyText(btn);
    expect(btn.textContent).toBe('[]');
  });

  test('copyUILog cambia texto a copiado', async () => {
    const btn = { textContent: 'copy' };
    KairosDebugPanel.copyUILog(btn);
    await new Promise(r => setTimeout(r, 10));
    expect(btn.textContent).toBe('copiado');
  });

  test('copyStreamLog cambia texto a copiado', async () => {
    const btn = { textContent: 'copy' };
    KairosDebugPanel.copyStreamLog(btn);
    await new Promise(r => setTimeout(r, 10));
    expect(btn.textContent).toBe('copiado');
  });

  test('copyWidgetLog sin widgets debug muestra []', () => {
    const btn = { textContent: 'copy' };
    KairosDebugPanel.copyWidgetLog(btn);
    expect(btn.textContent).toBe('[]');
  });
});
