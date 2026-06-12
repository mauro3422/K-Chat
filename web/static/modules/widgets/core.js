/**
 * Kairos Widgets — Core
 *
 * Estado global, utilidades básicas y extracción de widgets del markdown.
 */
import C from '../dom-contracts.js';
import stateManager from './state-manager.js';
import { getLogger } from '../logger.js';
var clog = getLogger('widgets-core');
let _registry = {};
let _debug = {};
let _index = 0;

export function nextIndex() {
    return _index++;
}

export function fnv1a_32(str) {
    var utf8 = unescape(encodeURIComponent(str));
    var h = 2166136261;
    for (var i = 0; i < utf8.length; i++) {
        h = h ^ utf8.charCodeAt(i);
        h = Math.imul(h, 16777619) >>> 0;
    }
    return ('00000000' + h.toString(16)).slice(-8);
}

export function log(id, label, detail) {
    _debug[id] = _debug[id] || { events: [] };
    _debug[id].events.push({
        t: Date.now(),
        label: label,
        detail: String(detail || '').substring(0, 200)
    });
    if (_debug[id].events.length > 50) _debug[id].events.shift();
    try { logUI('[W] ' + id, label + ' ' + String(detail || '').substring(0, 120)); } catch(e) {}
}

export function extract(text) {
    // 1. Parse markdown code blocks with an optional key: ```html-widget [key]
    var widgetRegex = /```html-widget(?:\s+([\w\-]+))?\s*\n([\s\S]*?)(?:\n```|$)/g;
    text = text.replace(widgetRegex, function(match, key, code) {
        var id = 'widget-' + nextIndex();
        code = code.replace(/\?\.([\w.]+)\s*=(?!=)/g, '.$1 =');
        _registry[id] = code;
        if (key && code) {
            stateManager.setCodeCache(key, code);
        }
        if (key) {
            clog.debug('extract_cb', { id: id, key: key, codeLen: code.length });
            return '<div class="' + C.WIDGET_CONTAINER + '" data-widget-id="' + id + '" data-widget-key="' + key + '"></div>';
        }
        clog.debug('extract_cb', { id: id, key: null, codeLen: code.length });
        return '<div class="' + C.WIDGET_CONTAINER + '" data-widget-id="' + id + '"></div>';
    });

    // 2. Parse inline tags like [Widget: key] or [Widget key] to load saved widgets
    var tagRegex = /\[Widget:?\s*([\w\-]+)\]/gi;
    var seenKeys = {};
    text = text.replace(tagRegex, function(match, key) {
        var lowerKey = key.toLowerCase();
        if (seenKeys[lowerKey]) {
            return '';
        }
        seenKeys[lowerKey] = true;
        var id = 'widget-' + nextIndex();
        clog.debug('extract_tag', { id: id, key: key });
        return '<div class="' + C.WIDGET_CONTAINER + '" data-widget-id="' + id + '" data-widget-key="' + key + '"></div>';
    });

    return text;
}

export function reset() {
    _registry = {};
    _index = 0;
    log('system', 'reset', 'registro de widgets y contador reseteados');
}

export const KairosWidgets = {
    get _registry() { return _registry; },
    get registry() { return _registry; },
    get _debug() { return _debug; },
    get debug() { return _debug; },
    get _index() { return _index; },
    get index() { return _index; },
    nextIndex,
    fnv1a_32,
    log,
    extract,
    reset
};
window.KairosWidgets = KairosWidgets;
