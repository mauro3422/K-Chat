/**
 * Kairos Widgets — Core
 *
 * Estado global, utilidades básicas y extracción de widgets del markdown.
 */
window.KairosWidgets = (function(api) {
    api._registry = {};
    api._debug = {};
    api._index = 0;

    api.nextIndex = function() {
        return api._index++;
    };

    api.fnv1a_32 = function(str) {
        var utf8 = unescape(encodeURIComponent(str));
        var h = 2166136261;
        for (var i = 0; i < utf8.length; i++) {
            h = h ^ utf8.charCodeAt(i);
            h = Math.imul(h, 16777619) >>> 0;
        }
        return ('00000000' + h.toString(16)).slice(-8);
    };

    api.log = function(id, label, detail) {
        api._debug[id] = api._debug[id] || { events: [] };
        api._debug[id].events.push({
            t: Date.now(),
            label: label,
            detail: String(detail || '').substring(0, 200)
        });
        if (api._debug[id].events.length > 50) api._debug[id].events.shift();
        try { logUI('[W] ' + id, label + ' ' + String(detail || '').substring(0, 120)); } catch(e) {}
    };

    api.extract = function(text) {
        // 1. Parse markdown code blocks with an optional key: ```html-widget [key]
        var widgetRegex = /```html-widget(?:\s+([\w\-]+))?\s*\n([\s\S]*?)(?:\n```|$)/g;
        text = text.replace(widgetRegex, function(match, key, code) {
            var id = 'widget-' + api.nextIndex();
            code = code.replace(/\?\.([\w.]+)\s*=(?!=)/g, '.$1 =');
            api._registry[id] = code;
            if (key) {
                return '<div class="interactive-widget-container" data-widget-id="' + id + '" data-widget-key="' + key + '"></div>';
            }
            return '<div class="interactive-widget-container" data-widget-id="' + id + '"></div>';
        });

        // 2. Parse inline tags like [Widget: key] or [Widget key] to load saved widgets
        var tagRegex = /\[Widget:?\s*([\w\-]+)\]/gi;
        text = text.replace(tagRegex, function(match, key) {
            var id = 'widget-' + api.nextIndex();
            return '<div class="interactive-widget-container" data-widget-id="' + id + '" data-widget-key="' + key + '"></div>';
        });

        return text;
    };

    api.reset = function() {
        api._registry = {};
        api._index = 0;
        api.log('system', 'reset', 'registro de widgets y contador reseteados');
    };

    return api;
})(window.KairosWidgets || {});
