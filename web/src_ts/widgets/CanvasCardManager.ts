import { IIframeBuilder } from '../types/iframe';
import { IWidgetRegistry, ICanvasCardManager, CardLayout } from '../types/widgets';
import { IEventBus } from '../types/events';
import { IDebugManager } from '../types/debug';
import { getLogger } from '../core/LoggerFactory';
import { ILogger } from '../core/Logger';

export class CanvasCardManager implements ICanvasCardManager {
  private cards = new Map<string, HTMLElement>();
  private codes = new Map<string, string>();
  private highestZIndex = 10;
  private logger: ILogger;

  onLayoutChange?: () => void;

  constructor(
    private canvasEl: HTMLElement,
    private cardsContainer: HTMLElement,
    private iframeBuilder: IIframeBuilder,
    private registry: IWidgetRegistry,
    private eventBus: IEventBus,
    private debug?: IDebugManager,
  ) {
    this.logger = getLogger('canvas-cards');
  }

  addCard(key: string, code: string, layout?: Partial<CardLayout>): HTMLElement | null {
    if (this.cards.has(key)) return null;

    this.codes.set(key, code);

    const cardH = layout?.h ?? 220;
    const minimized = layout?.minimized ?? false;

    const card = document.createElement('div');
    card.className = 'canvas-card';
    card.dataset.widgetKey = key;
    card.dataset.contentHeight = String(cardH);
    card.style.left = (layout?.x ?? 20) + 'px';
    card.style.top = (layout?.y ?? 20) + 'px';
    card.style.width = (layout?.w ?? 300) + 'px';
    card.style.height = minimized ? '40px' : cardH + 'px';
    if (minimized) card.classList.add('minimized');

    const header = document.createElement('div');
    header.className = 'canvas-card-header';

    const title = document.createElement('div');
    title.className = 'canvas-card-title';
    title.textContent = key;
    header.appendChild(title);

    const controls = document.createElement('div');
    controls.className = 'canvas-card-controls';

    const minimizeBtn = document.createElement('button');
    minimizeBtn.className = 'canvas-card-btn';
    minimizeBtn.innerHTML = minimized ? '🗖' : '🗕';
    minimizeBtn.title = minimized ? 'Restaurar' : 'Minimizar';
    controls.appendChild(minimizeBtn);

    const closeBtn = document.createElement('button');
    closeBtn.className = 'canvas-card-btn';
    closeBtn.innerHTML = '&times;';
    closeBtn.title = 'Desanclar del lienzo';
    controls.appendChild(closeBtn);

    header.appendChild(controls);
    card.appendChild(header);

    const body = document.createElement('div');
    body.className = 'canvas-card-body';
    this.iframeBuilder.createCanvasIframe(body, key, code);
    card.appendChild(body);

    const resizer = document.createElement('div');
    resizer.className = 'canvas-card-resizer';
    card.appendChild(resizer);

    this.cardsContainer.appendChild(card);
    this.cards.set(key, card);

    this.bindZIndexOnClick(card);
    this.bindDrag(card);
    this.bindResize(card, resizer);
    this.bindMinimize(card, key, minimizeBtn);
    this.bindClose(card, key, closeBtn);

    this.logger.info('card_added', `key=${key}`);
    return card;
  }

  removeCard(key: string): void {
    const card = this.cards.get(key);
    if (!card) return;
    card.remove();
    this.cards.delete(key);
    this.codes.delete(key);
    this.eventBus.emit('widget:unpinned', { widgetKey: key });
    this.onLayoutChange?.();
    this.logger.info('card_removed', `key=${key}`);
  }

  getCardLayouts(): CardLayout[] {
    const layouts: CardLayout[] = [];
    this.cards.forEach((card, key) => {
      const code = this.codes.get(key) || '';
      layouts.push({
        key,
        x: parseInt(card.style.left, 10) || 0,
        y: parseInt(card.style.top, 10) || 0,
        w: parseInt(card.style.width, 10) || 300,
        h: parseInt(card.dataset.contentHeight || card.style.height, 10) || 220,
        minimized: card.classList.contains('minimized'),
        code,
      });
    });
    return layouts;
  }

  clear(): void {
    this.cards.forEach(card => card.remove());
    this.cards.clear();
    this.codes.clear();
  }

  isPinned(key: string): boolean {
    return this.cards.has(key);
  }

  bringToFront(key: string): void {
    const card = this.cards.get(key);
    if (!card) return;
    this.highestZIndex += 2;
    card.style.zIndex = String(this.highestZIndex);
    card.classList.add('active-drag');
    setTimeout(() => card.classList.remove('active-drag'), 800);
  }

  getCard(key: string): HTMLElement | null {
    return this.cards.get(key) ?? null;
  }

  // ── Event bindings ─────────────────────────────────

  private bindZIndexOnClick(card: HTMLElement): void {
    card.addEventListener('mousedown', () => {
      this.highestZIndex += 2;
      card.style.zIndex = String(this.highestZIndex);
    });
  }

  private bindDrag(card: HTMLElement): void {
    const header = card.querySelector('.canvas-card-header') as HTMLElement;
    if (!header) return;

    header.addEventListener('mousedown', (e) => {
      if ((e.target as HTMLElement).closest('.canvas-card-btn')) return;
      e.preventDefault();

      card.classList.add('active-drag');
      const container = this.cardsContainer;

      const startX = e.clientX;
      const startY = e.clientY;
      const startLeft = card.offsetLeft;
      const startTop = card.offsetTop;

      const onMouseMove = (ev: MouseEvent) => {
        const dx = ev.clientX - startX;
        const dy = ev.clientY - startY;
        let l = startLeft + dx;
        let t = startTop + dy;
        l = Math.max(0, Math.min(l, container.clientWidth - card.clientWidth));
        t = Math.max(0, Math.min(t, container.clientHeight - card.clientHeight));
        requestAnimationFrame(() => {
          card.style.left = l + 'px';
          card.style.top = t + 'px';
        });
      };

      const onMouseUp = () => {
        card.classList.remove('active-drag');
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        this.onLayoutChange?.();
        this.logger.info('card_dragged', `key=${card.dataset.widgetKey} pos=${card.style.left},${card.style.top}`);
      };

      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    });
  }

  private bindResize(card: HTMLElement, resizer: HTMLElement): void {
    resizer.addEventListener('mousedown', (e) => {
      e.preventDefault();
      e.stopPropagation();

      const startX = e.clientX;
      const startY = e.clientY;
      const startW = card.clientWidth;
      const startH = card.clientHeight;

      const onMouseMove = (ev: MouseEvent) => {
        const dx = ev.clientX - startX;
        const dy = ev.clientY - startY;
        let w = startW + dx;
        let h = startH + dy;
        w = Math.max(200, w);
        if (!card.classList.contains('minimized')) {
          card.style.height = h + 'px';
          card.dataset.contentHeight = String(Math.max(60, Math.round(h)));
        }
        card.style.width = w + 'px';
      };

      const onMouseUp = () => {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        this.onLayoutChange?.();
        this.logger.info('card_resized', `key=${card.dataset.widgetKey} size=${card.style.width}x${card.style.height}`);
      };

      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    });
  }

  private bindMinimize(card: HTMLElement, key: string, btn: HTMLElement): void {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isMin = card.classList.toggle('minimized');
      const restoreH = parseInt(card.dataset.contentHeight || '220', 10);
      card.style.height = isMin ? '40px' : restoreH + 'px';
      btn.innerHTML = isMin ? '🗖' : '🗕';
      btn.title = isMin ? 'Restaurar' : 'Minimizar';
      this.onLayoutChange?.();
      this.logger.info('card_min_toggle', `key=${key} minimized=${isMin}`);
    });
  }

  private bindClose(card: HTMLElement, key: string, btn: HTMLElement): void {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      this.removeCard(key);
    });
  }
}
