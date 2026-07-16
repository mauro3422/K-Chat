import { describe, expect, it } from 'vitest';
import { WidgetDetector } from '../core/widget/WidgetDetector';
import { WidgetRegistry } from '../core/widget/WidgetRegistry';

describe('WidgetDetector', () => {
  it('returns only newly completed markers across feed calls', () => {
    const registry = new WidgetRegistry();
    const detector = new WidgetDetector(registry);

    const first = detector.feed('before ```html-widget demo\n<button>A</button>\n``` middle ');
    expect(first).toHaveLength(1);
    expect(first[0]).toMatchObject({
      type: 'block',
      key: 'demo',
      code: '<button>A</button>',
    });

    const second = detector.feed('and [Widget: chart]');
    expect(second).toHaveLength(1);
    expect(second[0]).toMatchObject({
      type: 'tag',
      key: 'chart',
    });
  });

  it('detects widget markers in hasWidgets for both blocks and tags', () => {
    const detector = new WidgetDetector(new WidgetRegistry());

    expect(detector.hasWidgets('plain text')).toBe(false);
    expect(detector.hasWidgets('[Widget: chart]')).toBe(true);
    expect(detector.hasWidgets('```html-widget demo\ncode\n```')).toBe(true);
  });

  it('extracts code for block markers and returns null for tags', () => {
    const detector = new WidgetDetector(new WidgetRegistry());
    const markers = detector.feed('```html-widget demo\n<button>A</button>\n``` [Widget: chart]');

    const block = markers.find(marker => marker.type === 'block');
    const tag = markers.find(marker => marker.type === 'tag');

    expect(block).toBeDefined();
    expect(tag).toBeDefined();
    expect(block ? detector.extractCode('', block) : null).toBe('<button>A</button>');
    expect(tag ? detector.extractCode('', tag) : null).toBeNull();
  });
});
