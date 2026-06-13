/**
 * Kairos Widgets — Core
 *
 * Estado global, utilidades básicas y extracción de widgets del markdown.
 */
import C from '../dom-contracts.js';
import stateManager from './state-manager.js';
import { INLINE_WIDGET_BLOCK_RE, INLINE_WIDGET_TAG_RE, normalizeWidgetCode } from './contract.js';
import { getLogger } from '../logger.js';
import { logUI } from '../log-ui.js';
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
    // Find all standard code blocks and inline code blocks that are NOT widgets
    var ignoredRanges = [];
    var codeBlockRegex = /```(html-widget)?[\s\S]*?(?:```|$)/g;
    var match;
    while ((match = codeBlockRegex.exec(text)) !== null) {
        if (!match[1]) {
            ignoredRanges.push({ start: match.index, end: match.index + match[0].length });
        }
    }
    var inlineRegex = /`[^`\n]+`/g;
    while ((match = inlineRegex.exec(text)) !== null) {
        ignoredRanges.push({ start: match.index, end: match.index + match[0].length });
    }

    function isIgnored(idx) {
        for (var i = 0; i < ignoredRanges.length; i++) {
            var range = ignoredRanges[i];
            if (idx >= range.start && idx < range.end) {
                return true;
            }
        }
        return false;
    }

    // 1. Parse markdown code blocks with an optional key: ```html-widget [key]
    INLINE_WIDGET_BLOCK_RE.lastIndex = 0;
    text = text.replace(INLINE_WIDGET_BLOCK_RE, function(match, key, code, offset) {
        if (isIgnored(offset)) {
            return match;
        }
        var id = 'widget-' + nextIndex();
        code = normalizeWidgetCode(code);
        _registry[id] = code;
        if (key && code) {
            stateManager.setCodeCache(key, code);
        }
        return '<div class="' + C.WIDGET_CONTAINER + '" data-widget-id="' + id + '"' + (key ? ' data-widget-key="' + key + '"' : '') + '></div>';
    });

    // 2. Parse inline tags like [Widget: key] or [Widget key] to load saved widgets
    var seenKeys = {};
    INLINE_WIDGET_TAG_RE.lastIndex = 0;
    text = text.replace(INLINE_WIDGET_TAG_RE, function(match, key, offset) {
        if (isIgnored(offset)) {
            return match;
        }
        var lowerKey = key.toLowerCase();
        if (seenKeys[lowerKey]) {
            return '';
        }
        seenKeys[lowerKey] = true;
        var id = 'widget-' + nextIndex();
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
