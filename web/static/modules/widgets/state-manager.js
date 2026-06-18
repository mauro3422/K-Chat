import { WIDGET_STATE_CODE_PREFIX, widgetCodeEntryKey, isWidgetCodeEntry } from './contract.js';

export class WidgetStateManager {
  constructor() {
    this._state = new Map();
  }

  getState(id) {
    return this._state.has(id) ? this._state.get(id) : null;
  }

  setState(id, value) {
    this._state.set(id, value);
  }

  getCodeCache(key) {
    return this.getState(widgetCodeEntryKey(key));
  }

  setCodeCache(key, code) {
    this.setState(widgetCodeEntryKey(key), code);
  }

  loadFromJSON(json) {
    if (!json || typeof json !== 'object') return;
    for (const [key, value] of Object.entries(json)) {
      this._state.set(key, value);
    }
  }

  toJSON() {
    const out = {};
    for (const [key, value] of this._state.entries()) {
      out[key] = value;
    }
    return out;
  }

  clear() {
    this._state.clear();
  }

  has(id) {
    return this._state.has(id);
  }

  delete(id) {
    this._state.delete(id);
  }
}

export default new WidgetStateManager();
