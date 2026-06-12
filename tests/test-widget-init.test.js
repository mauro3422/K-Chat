import { describe, test, expect, beforeEach } from 'vitest';
import './setup.js';

global.document = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], createElement: () => ({ className: '', dataset: {}, innerHTML: '', style: {}, children: [], appendChild: function() {}, removeChild: function() {}, classList: { add: function() {} } }) };
global.window = { addEventListener: () => {}, widgetStates: {} };
global.logUI = () => {};
global.sessionId = 'test';
global.fetch = () => Promise.resolve();

const widgetsDir = new URL('../web/static/modules/widgets/', import.meta.url).pathname;
const coreModule = await import(`file://${widgetsDir}/core.js`);
const KairosWidgets = coreModule.KairosWidgets;
const iframeBuilder = await import(`file://${widgetsDir}/iframe-builder.js`);
await import(`file://${widgetsDir}/toolbar.js`);
const iframeModule = await import(`file://${widgetsDir}/iframe.js`);
await import(`file://${widgetsDir}/messaging.js`);
await import(`file://${widgetsDir}/index.js`);
const { setWidgetObserver } = iframeModule;

function makeContainer(id, key) {
    return {
        dataset: {},
        attributes: {},
        children: [],
        getAttribute: function(name) {
            var m = { 'data-widget-id': id || 'w-test', 'data-widget-key': key || null };
            return m[name] || null;
        },
        setAttribute: function(name, val) { this.attributes[name] = val; if (name.startsWith('data-')) this.dataset[name.slice(5)] = val; },
        classList: { contains: function() { return false; } },
        appendChild: function() { },
        removeChild: function() { },
        offsetHeight: 0,
        parentElement: null
    };
}

function makeScope(container) {
    return {
        className: 'msg-body',
        querySelectorAll: function(sel) {
            if (sel === '.interactive-widget-container') return [container];
            return [];
        }
    };
}

beforeEach(() => {
    KairosWidgets.reset();
    iframeModule.reset();
    setWidgetObserver({ observe: function() {} });
});

describe('Widget Init — WeakMap tracking', () => {
    test('initAll is idempotent: calling twice logs init only once', () => {
        var container = makeContainer('w-idem', 'idem-key');
        var scope = makeScope(container);

        iframeModule.initAll(scope);
        iframeModule.initAll(scope);

        var widget = KairosWidgets.debug['w-idem'];
        expect(widget).toBeDefined();
        var inits = widget.events.filter(function(e) { return e.label === 'init'; });
        expect(inits.length).toBe(1);
    });

    test('WeakMap tracks state even when DOM attributes are cleared', () => {
        var container = makeContainer('w-domclear', 'domclear-key');
        var scope = makeScope(container);

        // First call initializes
        window.KairosWidgets.initAll(scope);

        // Simulate content-handler destroying/recreating container: clear DOM attributes
        container.dataset = {};

        // Second call should still skip because WeakMap has the state
        window.KairosWidgets.initAll(scope);

        var widget = KairosWidgets.debug['w-domclear'];
        expect(widget).toBeDefined();
        var inits = widget.events.filter(function(e) { return e.label === 'init'; });
        expect(inits.length).toBe(1);
    });

    test('reset() clears the WeakMap', () => {
        var container = makeContainer('w-reset', 'reset-key');
        var scope = makeScope(container);

        // Initialize
        window.KairosWidgets.initAll(scope);

        var wm = iframeModule.getInitializedWidgets();
        expect(wm.has(container)).toBe(true);

        // Reset
        iframeModule.reset();

        // After reset, the container should no longer be tracked
        // (new WeakMap, so the old container reference won't be in it)
        var newWm = iframeModule.getInitializedWidgets();
        expect(newWm.has(container)).toBe(false);

        // Now initAll should log init again (fresh state)
        // Note: KairosWidgets.reset() clears registry+index but not _debug,
        // so we count total init events - should be 2 (one before reset, one after)
        KairosWidgets.reset();
        iframeModule.initAll(scope);

        var widget = KairosWidgets.debug['w-reset'];
        var inits = widget.events.filter(function(e) { return e.label === 'init'; });
        expect(inits.length).toBe(2);
    });

    test('lazy-load path sets observed=true, initialized=false', () => {
        var container = makeContainer('w-lazy', 'lazy-key');
        var scope = makeScope(container);

        // Set up observer so lazy path is taken
        setWidgetObserver({ observe: function() {} });

        window.KairosWidgets.initAll(scope);

        var wm = iframeModule.getInitializedWidgets();
        var state = wm.get(container);
        expect(state).toBeDefined();
        expect(state.observed).toBe(true);
        expect(state.initialized).toBe(false);
        expect(state.widgetId).toBe('w-lazy');
    });

    test('immediate path (forceImmediate) sets both to true', () => {
        var container = makeContainer('w-immed', 'immed-key');
        var scope = makeScope(container);

        // Even with observer set, forceImmediate=true should take immediate path
        setWidgetObserver({ observe: function() {} });

        iframeModule.initAll(scope, true);

        var wm = iframeModule.getInitializedWidgets();
        var state = wm.get(container);
        expect(state).toBeDefined();
        expect(state.observed).toBe(true);
        expect(state.initialized).toBe(true);
        expect(state.widgetId).toBe('w-immed');
    });

    test('no observer set -> immediate path', () => {
        var container = makeContainer('w-noobs', 'noobs-key');
        var scope = makeScope(container);

        // No observer set (null) -> immediate path
        setWidgetObserver(null);

        window.KairosWidgets.initAll(scope);

        var wm = iframeModule.getInitializedWidgets();
        var state = wm.get(container);
        expect(state).toBeDefined();
        expect(state.initialized).toBe(true);
        expect(state.observed).toBe(true);
    });

    test('getInitializedWidgets returns the WeakMap', () => {
        var wm = iframeModule.getInitializedWidgets();
        expect(wm).toBeDefined();
        expect(typeof wm.get).toBe('function');
        expect(typeof wm.set).toBe('function');
        expect(typeof wm.has).toBe('function');
    });
});
