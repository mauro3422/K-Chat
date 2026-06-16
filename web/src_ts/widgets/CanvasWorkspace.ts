import { IEventBus } from '../types/events';
import { IWidgetRegistry } from '../types/widgets';
import { IIframeBuilder } from '../types/iframe';
import { IDebugManager } from '../types/debug';
import { getLogger } from '../core/LoggerFactory';
import { ILogger } from '../core/Logger';
import { CanvasCardManager } from './CanvasCardManager';
import { CanvasLayoutStore } from './CanvasLayoutStore';

export interface ICanvasWorkspace {
  init(sessionId: string): void;
  reset(): void;
  pinWidget(containerEl: HTMLElement, widgetKey: string, code: string): void;
  isPinned(widgetKey: string): boolean;
}

export class CanvasWorkspace implements ICanvasWorkspace {
  private cardManager!: CanvasCardManager;
  private layoutStore = new CanvasLayoutStore();
  private canvasEl: HTMLElement | null = null;
  private gutterEl: HTMLElement | null = null;
  private toggleBtn: HTMLElement | null = null;
  private closeBtn: HTMLElement | null = null;
  private cardsContainer: HTMLElement | null = null;
  private currentSessionId: string | null = null;
  private logger: ILogger;

  constructor(
    private iframeBuilder: IIframeBuilder,
    private registry: IWidgetRegistry,
    private eventBus: IEventBus,
    private debug?: IDebugManager,
  ) {
    this.logger = getLogger('canvas');
  }

  init(sessionId: string): void {
    this.currentSessionId = sessionId;
    this.logger.info('init', `sessionId=${sessionId}`);

    this.canvasEl = document.getElementById('canvas-workspace');
    this.gutterEl = document.getElementById('canvas-gutter');
    this.toggleBtn = document.getElementById('canvas-toggle');
    this.closeBtn = document.getElementById('canvas-close');
    this.cardsContainer = document.getElementById('canvas-cards');

    if (!this.canvasEl) return;

    if (!this.cardManager && this.cardsContainer) {
      this.cardManager = new CanvasCardManager(
        this.canvasEl,
        this.cardsContainer,
        this.iframeBuilder,
        this.registry,
        this.eventBus,
        this.debug,
      );
      this.cardManager.onLayoutChange = () => this.saveLayout();
    }

    this.restorePanelState();
    this.bindToggle();
    this.bindClose();
    this.bindGutterResize();

    if (this.cardsContainer) {
      this.cardsContainer.textContent = '';
    }
    this.loadSavedLayout();
  }

  reset(): void {
    this.currentSessionId = null;
    this.cardManager?.clear();
    this.logger.info('reset');
  }

  pinWidget(containerEl: HTMLElement, widgetKey: string, code: string): void {
    if (!widgetKey) return;
    this.logger.info('pin_widget', `key=${widgetKey}`);

    if (!this.canvasEl || !this.cardsContainer) return;

    this.ensureCanvasOpen();

    const rect = containerEl.getBoundingClientRect();
    const clone = document.createElement('div');
    clone.className = 'fly-away-clone';
    clone.style.top = rect.top + 'px';
    clone.style.left = rect.left + 'px';
    clone.style.width = rect.width + 'px';
    clone.style.height = rect.height + 'px';
    clone.textContent = `Anclando ${widgetKey}...`;
    document.body.appendChild(clone);

    const index = document.querySelectorAll('#canvas-cards .canvas-card').length;
    const layout = {
      x: 20 + (index % 5) * 30,
      y: 20 + Math.floor(index / 5) * 30,
      w: 300,
      h: 220,
      minimized: false,
    };

    const targetRect = this.cardsContainer.getBoundingClientRect();
    const targetLeft = targetRect.left + layout.x;
    const targetTop = targetRect.top + layout.y;

    setTimeout(() => {
      clone.style.left = targetLeft + 'px';
      clone.style.top = targetTop + 'px';
      clone.style.width = layout.w + 'px';
      clone.style.height = layout.h + 'px';
      clone.style.opacity = '0.3';
    }, 50);

    clone.addEventListener('transitionend', () => {
      clone.remove();
      this.cardManager.addCard(widgetKey, code, layout);
      this.saveLayout();

      containerEl.textContent = '';
      const placeholder = document.createElement('a');
      placeholder.href = '#';
      placeholder.className = 'pinned-widget-placeholder';
      placeholder.dataset.widgetKey = widgetKey;
      placeholder.innerHTML = `<span class="pin-icon">📌</span> Widget anclado: <strong>${widgetKey}</strong> (Ver en Lienzo)`;
      placeholder.addEventListener('click', (e) => {
        e.preventDefault();
        this.cardManager.bringToFront(widgetKey);
      });
      containerEl.appendChild(placeholder);
    });
  }

  isPinned(widgetKey: string): boolean {
    return this.cardManager?.isPinned(widgetKey) ?? false;
  }

  // ── Panel state ──────────────────────────────────────

  private restorePanelState(): void {
    if (!this.currentSessionId || !this.canvasEl) return;
    const storedCollapsed = localStorage.getItem(`canvas_collapsed_${this.currentSessionId}`);
    const isCollapsed = storedCollapsed === null ? true : storedCollapsed === 'true';
    this.canvasEl.classList.toggle('collapsed', isCollapsed);
    this.gutterEl?.classList.toggle('collapsed', isCollapsed);
    this.toggleBtn?.classList.toggle('active', !isCollapsed);

    const savedWidth = localStorage.getItem(`canvas_width_${this.currentSessionId}`) || '400';
    if (!isCollapsed) this.canvasEl.style.width = savedWidth + 'px';
  }

  private ensureCanvasOpen(): void {
    if (!this.canvasEl || !this.currentSessionId) return;
    if (this.canvasEl.classList.contains('collapsed')) {
      this.canvasEl.classList.remove('collapsed');
      this.gutterEl?.classList.remove('collapsed');
      document.getElementById('canvas-toggle')?.classList.add('active');
      localStorage.setItem(`canvas_collapsed_${this.currentSessionId}`, 'false');
      const w = localStorage.getItem(`canvas_width_${this.currentSessionId}`) || '400';
      this.canvasEl.style.width = w + 'px';
    }
  }

  private bindToggle(): void {
    if (!this.toggleBtn || !this.canvasEl) return;
    this.toggleBtn.onclick = () => {
      const collapsed = this.canvasEl!.classList.toggle('collapsed');
      this.gutterEl?.classList.toggle('collapsed', collapsed);
      this.toggleBtn!.classList.toggle('active', !collapsed);
      if (this.currentSessionId) {
        localStorage.setItem(`canvas_collapsed_${this.currentSessionId}`, String(collapsed));
      }
      if (!collapsed && this.currentSessionId) {
        const w = localStorage.getItem(`canvas_width_${this.currentSessionId}`) || '400';
        this.canvasEl!.style.width = w + 'px';
      }
    };
  }

  private bindClose(): void {
    if (!this.closeBtn || !this.canvasEl) return;
    this.closeBtn.onclick = () => {
      this.canvasEl!.classList.add('collapsed');
      this.gutterEl?.classList.add('collapsed');
      document.getElementById('canvas-toggle')?.classList.remove('active');
      if (this.currentSessionId) {
        localStorage.setItem(`canvas_collapsed_${this.currentSessionId}`, 'true');
      }
    };
  }

  private bindGutterResize(): void {
    if (!this.gutterEl || !this.canvasEl) return;
    this.gutterEl.onmousedown = (e: MouseEvent) => {
      e.preventDefault();
      this.gutterEl!.classList.add('dragging');

      const onMouseMove = (ev: MouseEvent) => {
        const app = document.getElementById('app');
        if (!app) return;
        const appW = app.clientWidth;
        let w = appW - ev.clientX;
        if (w < 250) w = 250;
        if (w > appW * 0.8) w = appW * 0.8;
        this.canvasEl!.style.width = w + 'px';
        if (this.currentSessionId) {
          localStorage.setItem(`canvas_width_${this.currentSessionId}`, String(w));
        }
      };

      const onMouseUp = () => {
        this.gutterEl!.classList.remove('dragging');
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
      };

      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    };
  }

  // ── Layout persistence ───────────────────────────────

  private saveLayout(): void {
    if (!this.currentSessionId) return;
    const layouts = this.cardManager.getCardLayouts();
    this.layoutStore.saveLayout(this.currentSessionId, layouts);
  }

  private loadSavedLayout(): void {
    if (!this.currentSessionId) return;
    const layouts = this.layoutStore.loadLayout(this.currentSessionId);
    for (const layout of layouts) {
      this.cardManager.addCard(layout.key, layout.code, layout);
    }
  }
}
