import { IDomRenderer } from '../types/rendering';
import { IWidgetRegistry } from '../types/widgets';
import { C } from '../core/infra/DomContracts';

/**
 * BrowserDomRenderer — renders Markdown → HTML using injected `marked` and `DOMPurify`.
 *
 * Calls registry.extract() BEFORE parsing to handle widget code blocks and
 * [Widget: key] tags.
 */
interface MarkedLib {
  parse: (text: string, opts?: Record<string, unknown>) => string;
}

interface DOMPurifyLib {
  sanitize: (html: string, config?: Record<string, unknown>) => string;
}

export interface MarkdownRendererDeps {
  markedFn: ((text: string) => string) | MarkedLib;
  dompurifyFn: DOMPurifyLib;
  widgetRegistry: IWidgetRegistry;
}

export class BrowserDomRenderer implements IDomRenderer {
  private markedFn: (text: string) => string;
  private dompurifyFn: { sanitize: (html: string, config?: Record<string, unknown>) => string };
  private widgetRegistry: IWidgetRegistry;

  constructor(
    markedFn: ((text: string) => string) | MarkedLib,
    dompurifyFn: DOMPurifyLib,
    widgetRegistry: IWidgetRegistry,
  ) {
    this.markedFn = (text: string) => {
      if (typeof markedFn === 'function') {
        return markedFn(text);
      }
      return markedFn.parse(text, { breaks: true, gfm: true });
    };
    this.dompurifyFn = dompurifyFn;
    this.widgetRegistry = widgetRegistry;
  }

  renderMessage(container: HTMLElement, content: string, isMarkdown: boolean): void {
    if (isMarkdown) {
      container.innerHTML = this.renderMarkdown(content);
    } else {
      container.textContent = content;
    }
  }

  renderReasoning(container: HTMLElement, text: string): void {
    const reasoningEl = container.querySelector('.' + C.REASONING + ' .' + C.RT);
    if (reasoningEl) {
      reasoningEl.textContent = text;
    }
  }

  renderToolCall(container: HTMLElement, data: unknown): void {
    // Tool calls are rendered by the ContentHandler now
  }

  clearThinking(container: HTMLElement): void {
    const body = container.querySelector('.' + C.MSG_BODY);
    if (body && (body.textContent === 'Pensando...' || body.textContent === '')) {
      body.textContent = '';
    }
  }

  /** Shared markdown renderer: extract() → markedFn() → DOMPurify.sanitize() */
  renderMarkdown(markdown: string): string {
    try {
      const extracted = this.widgetRegistry.extract(markdown);
      const rawHtml = this.markedFn(extracted);
      if (this.dompurifyFn && typeof this.dompurifyFn.sanitize === 'function') {
        return this.dompurifyFn.sanitize(rawHtml, {
          ADD_TAGS: ['iframe'],
          ADD_ATTR: ['allow', 'allowfullscreen', 'frameborder', 'scrolling',
                     'srcdoc', 'sandbox', 'data-widget-id', 'data-widget-key'],
        });
      }
      return rawHtml;
    } catch (e) {
      console.warn('[Markdown] parse error, falling back to text:', e);
    }
    return markdown
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br>');
  }
}

/** Standalone function for explicit markdown rendering with injected deps. */
export function renderMarkdown(text: string, deps: MarkdownRendererDeps): string {
  return new BrowserDomRenderer(deps.markedFn, deps.dompurifyFn, deps.widgetRegistry).renderMarkdown(text);
}
