import { describe, test, expect, beforeEach } from 'vitest';
import './setup.js';

// Override debug-specific mocks
global.navigator.clipboard = { writeText: () => Promise.resolve() };
global.sessionId = 'debug-test-sid';
global.Utils = { escHtml: (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') };
global.WidgetManager = { debug: {}, log: () => {} };
global.fetch = () => Promise.resolve({ json: () => Promise.resolve({}) });

const { DebugPanel } = await import('../web/static/modules/debug-panel.js');
DebugPanel.bindDebugControls();

describe('KairosDebug', () => {
  test('logUI guarda evento en uiEvents', async () => {
    DebugPanel.logUI('test-label', 'test-detail');
    const btn = { textContent: 'copy' };
    DebugPanel.copyUILog(btn);
    await new Promise(r => setTimeout(r, 10));
    expect(btn.textContent).toBe('copiado');
  });

  test('logUI con label vacio no lanza error', () => {
    expect(() => DebugPanel.logUI('', '')).not.toThrow();
  });

  test('logStream guarda evento en streamEvents', async () => {
    DebugPanel.logStream('content', 'texto de prueba');
    const btn = { textContent: 'copy' };
    DebugPanel.copyStreamLog(btn);
    await new Promise(r => setTimeout(r, 10));
    expect(btn.textContent).toBe('copiado');
  });

  test('logStream con data null no lanza error', () => {
    expect(() => DebugPanel.logStream('error', null)).not.toThrow();
  });

  test('logStream con objeto data no lanza error', () => {
    expect(() => DebugPanel.logStream('tool_call', { name: 'test', args: { x: 1 } })).not.toThrow();
  });

  test('toggleDebug abre panel primera vez', () => {
    const panelClasses = { _open: false, toggle(cls, val) { if (cls === 'open') this._open = val !== undefined ? val : !this._open; }, contains() { return this._open; } };
    const mainClasses = { _shifted: false, toggle(cls, val) { if (cls === 'shifted') this._shifted = val !== undefined ? val : !this._shifted; }, contains() { return this._shifted; } };
    global.document.getElementById = (id) => {
      if (id === 'debug-panel') return { classList: panelClasses };
      if (id === 'main') return { classList: mainClasses };
      return null;
    };
    DebugPanel.toggleDebug();
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
    DebugPanel.toggleDebug();
    expect(panelClasses._open).toBe(false);
  });

  test('toggleDebug sin DOM no lanza error', () => {
    global.document.getElementById = () => null;
    expect(() => { DebugPanel.toggleDebug(); DebugPanel.toggleDebug(); }).not.toThrow();
  });

  test('toggleDebug es una función exportada', () => {
    expect(typeof DebugPanel.toggleDebug).toBe('function');
  });

  test('copyText sin pre muestra []', () => {
    const btn = { textContent: 'copy', parentElement: { querySelector: () => null } };
    DebugPanel.copyText(btn);
    expect(btn.textContent).toBe('[]');
  });

  test('copyUILog cambia texto a copiado', async () => {
    const btn = { textContent: 'copy' };
    DebugPanel.copyUILog(btn);
    await new Promise(r => setTimeout(r, 10));
    expect(btn.textContent).toBe('copiado');
  });

  test('copyStreamLog cambia texto a copiado', async () => {
    const btn = { textContent: 'copy' };
    DebugPanel.copyStreamLog(btn);
    await new Promise(r => setTimeout(r, 10));
    expect(btn.textContent).toBe('copiado');
  });

  test('copyWidgetLog sin widgets debug muestra []', () => {
    const btn = { textContent: 'copy' };
    DebugPanel.copyWidgetLog(btn);
    expect(btn.textContent).toBe('[]');
  });
});
