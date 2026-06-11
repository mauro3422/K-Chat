import { describe, test, expect, beforeEach } from 'vitest';
import './setup.js';

const stateManagerPath = new URL('../web/static/modules/widgets/state-manager.js', import.meta.url).pathname;

describe('WidgetStateManager', () => {
    let WidgetStateManager;
    let instance;

    beforeEach(async () => {
        const mod = await import(`file://${stateManagerPath}?t=${Date.now()}`);
        WidgetStateManager = mod.WidgetStateManager;
        instance = new WidgetStateManager();
    });

    describe('getState / setState', () => {
        test('getState returns null for unknown id', () => {
            expect(instance.getState('nonexistent')).toBe(null);
        });

        test('setState and getState roundtrip with string', () => {
            instance.setState('widget-1', 'some-state');
            expect(instance.getState('widget-1')).toBe('some-state');
        });

        test('setState and getState roundtrip with object', () => {
            const state = { count: 5, items: ['a', 'b'] };
            instance.setState('widget-2', state);
            expect(instance.getState('widget-2')).toEqual(state);
        });

        test('setState and getState roundtrip with null', () => {
            instance.setState('widget-3', null);
            expect(instance.getState('widget-3')).toBe(null);
        });

        test('setState overwrites previous value', () => {
            instance.setState('widget-4', 'first');
            instance.setState('widget-4', 'second');
            expect(instance.getState('widget-4')).toBe('second');
        });

        test('different ids are independent', () => {
            instance.setState('a', 1);
            instance.setState('b', 2);
            expect(instance.getState('a')).toBe(1);
            expect(instance.getState('b')).toBe(2);
        });
    });

    describe('getCodeCache / setCodeCache', () => {
        test('getCodeCache returns null for unknown key', () => {
            expect(instance.getCodeCache('unknown-key')).toBe(null);
        });

        test('setCodeCache and getCodeCache roundtrip', () => {
            const code = '<div>hello</div>';
            instance.setCodeCache('my-widget', code);
            expect(instance.getCodeCache('my-widget')).toBe(code);
        });

        test('_code_ prefix is internal detail', () => {
            instance.setCodeCache('test-key', 'code-value');
            expect(instance.getState('_code_test-key')).toBe('code-value');
            expect(instance.getCodeCache('test-key')).toBe('code-value');
        });

        test('code cache is independent of regular state', () => {
            instance.setState('widget-x', 'regular-state');
            instance.setCodeCache('widget-x', 'cached-code');
            expect(instance.getState('widget-x')).toBe('regular-state');
            expect(instance.getCodeCache('widget-x')).toBe('cached-code');
        });
    });

    describe('loadFromJSON', () => {
        test('loads plain object into state', () => {
            instance.loadFromJSON({ 'w1': 'state1', 'w2': 'state2' });
            expect(instance.getState('w1')).toBe('state1');
            expect(instance.getState('w2')).toBe('state2');
        });

        test('MERGES with existing state (does not replace)', () => {
            instance.setState('existing', 'keep-me');
            instance.loadFromJSON({ 'new': 'added' });
            expect(instance.getState('existing')).toBe('keep-me');
            expect(instance.getState('new')).toBe('added');
        });

        test('MERGES overwrites conflicting keys', () => {
            instance.setState('shared', 'old');
            instance.loadFromJSON({ 'shared': 'new' });
            expect(instance.getState('shared')).toBe('new');
        });

        test('handles empty object', () => {
            instance.setState('a', 1);
            instance.loadFromJSON({});
            expect(instance.getState('a')).toBe(1);
        });

        test('handles null input gracefully', () => {
            instance.setState('a', 1);
            instance.loadFromJSON(null);
            expect(instance.getState('a')).toBe(1);
        });

        test('handles undefined input gracefully', () => {
            instance.setState('a', 1);
            instance.loadFromJSON(undefined);
            expect(instance.getState('a')).toBe(1);
        });

        test('loads _code_ prefixed entries', () => {
            instance.loadFromJSON({ '_code_mykey': 'cached-code' });
            expect(instance.getCodeCache('mykey')).toBe('cached-code');
        });
    });

    describe('toJSON', () => {
        test('serializes all state entries', () => {
            instance.setState('a', 1);
            instance.setState('b', 2);
            instance.setCodeCache('k', 'code');
            const json = instance.toJSON();
            expect(json).toEqual({ 'a': 1, 'b': 2, '_code_k': 'code' });
        });

        test('returns empty object when empty', () => {
            expect(instance.toJSON()).toEqual({});
        });

        test('roundtrip through loadFromJSON', () => {
            instance.setState('x', 'val');
            instance.setCodeCache('y', 'code');
            const json = instance.toJSON();
            const instance2 = new WidgetStateManager();
            instance2.loadFromJSON(json);
            expect(instance2.getState('x')).toBe('val');
            expect(instance2.getCodeCache('y')).toBe('code');
        });
    });

    describe('clear', () => {
        test('clear resets all state', () => {
            instance.setState('a', 1);
            instance.setCodeCache('b', 'code');
            instance.clear();
            expect(instance.getState('a')).toBe(null);
            expect(instance.getCodeCache('b')).toBe(null);
            expect(instance.toJSON()).toEqual({});
        });

        test('clear allows reuse', () => {
            instance.setState('a', 1);
            instance.clear();
            instance.setState('b', 2);
            expect(instance.getState('a')).toBe(null);
            expect(instance.getState('b')).toBe(2);
        });
    });

    describe('has / delete', () => {
        test('has returns true for existing key', () => {
            instance.setState('x', 1);
            expect(instance.has('x')).toBe(true);
        });

        test('has returns false for missing key', () => {
            expect(instance.has('x')).toBe(false);
        });

        test('delete removes entry', () => {
            instance.setState('x', 1);
            instance.delete('x');
            expect(instance.has('x')).toBe(false);
            expect(instance.getState('x')).toBe(null);
        });
    });

    describe('window.WidgetStateManager', () => {
        test('instance is exported to window', () => {
            expect(window.WidgetStateManager).toBeDefined();
            expect(typeof window.WidgetStateManager.getState).toBe('function');
            expect(typeof window.WidgetStateManager.setState).toBe('function');
        });
    });
});
