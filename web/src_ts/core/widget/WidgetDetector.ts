import { WidgetMarker } from '../../types/streaming';
import { IWidgetRegistry } from '../../types/widgets';

/**
 * WidgetDetector — shared widget contract and detection logic.
 *
 * Detects ```html-widget blocks and [Widget:key] tags in streamed text.
 * NOW INSTANCE-BASED: receives IWidgetRegistry via constructor.
 */
export class WidgetDetector {
  /** Regex for ```html-widget [key] \n ... \n``` blocks */
  private static BLOCK_RE = /```html-widget(?:\s+([\w\-]+))?\s*\n([\s\S]*?)(?:\n```|$)/g;

  /** Regex for [Widget:key] or [Widget key] inline tags */
  private static TAG_RE = /\[Widget:?\s*([\w\-]+)\]/gi;

  /** Full accumulated text being scanned */
  private accumulatedText = '';

  constructor(private registry: IWidgetRegistry) {}

  /** Feed new text chunk and return newly detected markers */
  feed(text: string): WidgetMarker[] {
    this.accumulatedText += text;
    return this.scan();
  }

  /** Reset accumulated text (e.g. on new message) */
  reset(): void {
    this.accumulatedText = '';
  }

  /** Scan accumulated text for widget markers */
  private scan(): WidgetMarker[] {
    const markers: WidgetMarker[] = [];

    // Find ```html-widget blocks
    WidgetDetector.BLOCK_RE.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = WidgetDetector.BLOCK_RE.exec(this.accumulatedText)) !== null) {
      const key = match[1] || undefined;
      const code = match[2].trim();
      if (!code) continue;

      // Register the code via injected registry
      this.registry.register(code, key);

      markers.push({
        type: 'block',
        key,
        code,
        startPos: match.index,
        endPos: match.index + match[0].length,
      });
    }

    // Find [Widget:key] tags
    WidgetDetector.TAG_RE.lastIndex = 0;
    while ((match = WidgetDetector.TAG_RE.exec(this.accumulatedText)) !== null) {
      markers.push({
        type: 'tag',
        key: match[1],
        startPos: match.index,
        endPos: match.index + match[0].length,
      });
    }

    return markers;
  }

  /** Check if text contains any widget markers */
  hasWidgets(text: string): boolean {
    WidgetDetector.BLOCK_RE.lastIndex = 0;
    return WidgetDetector.BLOCK_RE.test(text);
  }

  /** Extract a widget code block from text at a specific position */
  extractCode(text: string, marker: WidgetMarker): string | null {
    if (marker.type === 'tag') {
      // Look up code by key via registry
      const id = Object.keys(this.registry.getRegistry()).find(
        k => this.registry.getRegistry()[k] && k.includes('widget-')
      );
      return marker.key ? this.registry.getCode(`_code_${marker.key}`) || null : null;
    }
    return marker.code || null;
  }
}
