import { describe, test, expect } from 'vitest';
import './setup.js';
import {
  WIDGET_STATE_CODE_PREFIX,
  widgetCodeEntryKey,
  normalizeWidgetCode,
  isWidgetCodeEntry,
} from '../web/static/modules/widgets/contract.js';

describe('widget contract', () => {
  test('normalizes widget code the same way the renderer expects', () => {
    expect(normalizeWidgetCode('obj?.foo.bar = 1;')).toBe('obj.foo.bar = 1;');
  });

  test('builds code entry keys with the shared prefix', () => {
    expect(widgetCodeEntryKey('calc')).toBe(`${WIDGET_STATE_CODE_PREFIX}calc`);
    expect(isWidgetCodeEntry('_code_calc')).toBe(true);
    expect(isWidgetCodeEntry('calc')).toBe(false);
  });
});
