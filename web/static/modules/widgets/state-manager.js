/**
 * WidgetStateManager — Centralized widget state management
 *
 * Replaces scattered window.widgetStates reads/writes with a single
 * coordinated manager. Handles _code_ prefix internally.
 */
import { WIDGET_STATE_CODE_PREFIX } from './contract.js';

class WidgetStateManager {
    constructor() {
        this._store = new Map();
    }

    getState(id) {
        return this._store.get(id) ?? null;
    }

    setState(id, state) {
        this._store.set(id, state);
    }

    getCodeCache(key) {
        return this._store.get(WIDGET_STATE_CODE_PREFIX + key) ?? null;
    }

    setCodeCache(key, code) {
        this._store.set(WIDGET_STATE_CODE_PREFIX + key, code);
    }

    loadFromJSON(json) {
        if (!json || typeof json !== 'object') return;
        for (const [k, v] of Object.entries(json)) {
            this._store.set(k, v);
        }
    }

    toJSON() {
        const obj = {};
        for (const [k, v] of this._store) {
            obj[k] = v;
        }
        return obj;
    }

    clear() {
        this._store.clear();
    }

    has(id) {
        return this._store.has(id);
    }

    delete(id) {
        this._store.delete(id);
    }
}

const instance = new WidgetStateManager();

export { WidgetStateManager };
export default instance;

