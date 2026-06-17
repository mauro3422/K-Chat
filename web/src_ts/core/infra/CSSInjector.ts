import { ICSSInjector } from '../../types/layout';
import { getLogger } from './LoggerFactory';
import { ILogger } from './Logger';

export class CSSInjector implements ICSSInjector {
  private logger: ILogger;
  private styles = new Map<string, HTMLStyleElement>();

  constructor() {
    this.logger = getLogger('css-injector');
  }

  inject(id: string, css: string): HTMLStyleElement {
    this.remove(id);
    const style = document.createElement('style');
    style.id = `k-inject-${id}`;
    style.textContent = css;
    document.head.appendChild(style);
    this.styles.set(id, style);
    this.logger.info('inject', `id=${id} len=${css.length}`);
    return style;
  }

  remove(id: string): void {
    const existing = this.styles.get(id);
    if (existing) {
      existing.remove();
      this.styles.delete(id);
      this.logger.info('remove', `id=${id}`);
    }
    const domEl = document.getElementById(`k-inject-${id}`);
    domEl?.remove();
  }

  has(id: string): boolean {
    return this.styles.has(id) || !!document.getElementById(`k-inject-${id}`);
  }

  clear(): void {
    this.styles.forEach((style) => style.remove());
    this.styles.clear();
    this.logger.info('clear');
  }
}
