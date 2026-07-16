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
  private static BLOCK_RE = /```html-widget(?:\s+([\w\-]+))?\s*\n([\s\S]*?)\n```/g;

  /** Regex for [Widget:key] or [Widget key] inline tags */
  private static TAG_RE = /\[Widget:?\s*([\w\-]+)\]/gi;

  /** Full accumulated text being scanned */
  private accumulatedText = '';

  constructor(private registry: IWidgetRegistry) {}

  /** Feed new text chunk and return newly detected markers */
  feed(text: string): WidgetMarker[] {
    const previousLength = this.accumulatedText.length;
    this.accumulatedText += text;
    return this.scan(previousLength);
  }

  /** Reset accumulated text (e.g. on new message) */
  reset(): void {
    this.accumulatedText = '';
  }

  /** Scan accumulated text for widget markers */
  private scan(previousLength: number): WidgetMarker[] {
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

    return markers.filter(marker => marker.endPos > previousLength);
  }

  /** Check if text contains any widget markers */
  hasWidgets(text: string): boolean {
    WidgetDetector.BLOCK_RE.lastIndex = 0;
    if (WidgetDetector.BLOCK_RE.test(text)) return true;
    WidgetDetector.TAG_RE.lastIndex = 0;
    return WidgetDetector.TAG_RE.test(text);
  }

  /** Extract a widget code block from text at a specific position */
  extractCode(text: string, marker: WidgetMarker): string | null {
    if (marker.type === 'tag') {
      return null;
    }
    return marker.code || null;
  }
}
