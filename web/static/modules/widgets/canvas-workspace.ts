/**
 * K-Chat Canvas Workspace Logic
 * Controls widget dashboard panel, drag & drop, resizing, state persistence, and fly-away transitions.
 */
import { getLogger } from '../logger.js';
import { ApiClient } from '../api-client.js';
import { WidgetManager } from './index.js';
import stateManager from './state-manager.js';
import { createIframe } from './iframe-builder.js';

const log = getLogger('canvas-workspace');
let _currentSessionId: string | null = null;
let _highestZIndex: number = 10;
const _pinnedWidgetKeys = new Set<string>(); // Keep track of widget keys pinned in this session

interface CardLayout {
  left: number;
  top: number;
  width: number;
  height: number;
  minimized: boolean;
}

export const CanvasWorkspace = {
  init(sessionId: string): void {
    _currentSessionId = sessionId;
    _pinnedWidgetKeys.clear();
    
    // Bind toggle buttons
    const toggleBtn = document.getElementById('canvas-toggle');
    const closeBtn = document.getElementById('canvas-close');
    const canvasEl = document.getElementById('canvas-workspace');
    const gutterEl = document.getElementById('canvas-gutter');
    
    if (!canvasEl) return;
    
    // Load state of collapsed canvas from localStorage (defaults to true/collapsed if null)
    const storedCollapsed = localStorage.getItem(`canvas_collapsed_${_currentSessionId}`);
    const isCollapsed = storedCollapsed === null ? true : storedCollapsed === 'true';
    if (isCollapsed) {
      canvasEl.classList.add('collapsed');
      gutterEl?.classList.add('collapsed');
      toggleBtn?.classList.remove('active');
    } else {
      canvasEl.classList.remove('collapsed');
      gutterEl?.classList.remove('collapsed');
      toggleBtn?.classList.add('active');
    }
    
    // Load saved width
    const savedWidth = localStorage.getItem(`canvas_width_${_currentSessionId}`) || '400';
    if (!isCollapsed) {
      canvasEl.style.width = savedWidth + 'px';
    }
    
    // Toggle actions
    if (toggleBtn) {
      // Clear previous listeners to prevent duplicates
      const newToggleBtn = toggleBtn.cloneNode(true) as HTMLElement;
      toggleBtn.parentNode?.replaceChild(newToggleBtn, toggleBtn);
      newToggleBtn.addEventListener('click', () => {
        const collapsed = canvasEl.classList.toggle('collapsed');
        gutterEl?.classList.toggle('collapsed', collapsed);
        newToggleBtn.classList.toggle('active', !collapsed);
        localStorage.setItem(`canvas_collapsed_${_currentSessionId}`, String(collapsed));
        if (!collapsed) {
          const w = localStorage.getItem(`canvas_width_${_currentSessionId}`) || '400';
          canvasEl.style.width = w + 'px';
        }
      });
    }
    
    if (closeBtn) {
      const newCloseBtn = closeBtn.cloneNode(true) as HTMLElement;
      closeBtn.parentNode?.replaceChild(newCloseBtn, closeBtn);
      newCloseBtn.addEventListener('click', () => {
        canvasEl.classList.add('collapsed');
        gutterEl?.classList.add('collapsed');
        document.getElementById('canvas-toggle')?.classList.remove('active');
        localStorage.setItem(`canvas_collapsed_${_currentSessionId}`, 'true');
      });
    }
    
    // Gutter Resizer binding
    if (gutterEl) {
      const newGutterEl = gutterEl.cloneNode(true) as HTMLElement;
      gutterEl.parentNode?.replaceChild(newGutterEl, gutterEl);
      newGutterEl.addEventListener('mousedown', (e: MouseEvent) => {
        e.preventDefault();
        newGutterEl.classList.add('dragging');
        
        function onMouseMove(ev: MouseEvent) {
          const app = document.getElementById('app');
          if (!app) return;
          const appW = app.clientWidth;
          let w = appW - ev.clientX;
          if (w < 250) w = 250;
          if (w > appW * 0.8) w = appW * 0.8;
          if (canvasEl) {
            canvasEl.style.width = w + 'px';
          }
          localStorage.setItem(`canvas_width_${_currentSessionId}`, String(w));
        }
        
        function onMouseUp() {
          newGutterEl.classList.remove('dragging');
          document.removeEventListener('mousemove', onMouseMove);
          document.removeEventListener('mouseup', onMouseUp);
        }
        
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
      });
    }
    
    // Clean canvas container
    const cardsContainer = document.getElementById('canvas-cards');
    if (cardsContainer) {
      cardsContainer.textContent = '';
    }
    
    // Load saved layouts
    this.loadSavedLayout();
  },
  
  loadSavedLayout(): void {
    if (!_currentSessionId) return;
    try {
      const layoutData = JSON.parse(localStorage.getItem(`canvas_layout_${_currentSessionId}`) || '{}') as Record<string, CardLayout>;
      const cardsContainer = document.getElementById('canvas-cards');
      if (!cardsContainer) return;
      
      // Look for widgets in the current session
      ApiClient.loadMessages(_currentSessionId)
        .then((r: any) => r.json())
        .then((data: any) => {
          const widgetStates = data.widget_states || {};
          const widgetKeys = Object.keys(widgetStates).filter(k => !k.startsWith('_'));
          
          // Recreate saved widgets on canvas
          widgetKeys.forEach((key, index) => {
            const cardLayout = layoutData[key] || {
              left: 20 + (index % 5) * 30,
              top: 20 + Math.floor(index / 5) * 30,
              width: 300,
              height: 220,
              minimized: false
            };
            
            // Get code for this widget from code state keys
            const widgetCode = widgetStates[key] || '';
            if (widgetCode && (widgetCode.includes('<div') || widgetCode.includes('<script'))) {
              this.addCardToCanvas(key, widgetCode, cardLayout);
            }
          });
        });
    } catch(e) {
      log.error('Failed to load canvas layout', e);
    }
  },
  
  saveSavedLayout(): void {
    if (!_currentSessionId) return;
    const layout: Record<string, CardLayout> = {};
    const cards = document.querySelectorAll('#canvas-cards .canvas-card');
    cards.forEach(cardNode => {
      const card = cardNode as HTMLElement;
      const key = card.dataset.widgetKey;
      if (key) {
        layout[key] = {
          left: parseInt(card.style.left, 10) || 0,
          top: parseInt(card.style.top, 10) || 0,
          width: parseInt(card.style.width, 10) || 300,
          height: parseInt(card.style.height, 10) || 220,
          minimized: card.classList.contains('minimized')
        };
      }
    });
    localStorage.setItem(`canvas_layout_${_currentSessionId}`, JSON.stringify(layout));
  },
  
  addCardToCanvas(widgetKey: string, code: string, layout: CardLayout): void {
    const cardsContainer = document.getElementById('canvas-cards');
    if (!cardsContainer) return;
    
    // Check if card already exists
    if (cardsContainer.querySelector(`.canvas-card[data-widget-key="${widgetKey}"]`)) {
      return;
    }
    
    _pinnedWidgetKeys.add(widgetKey);
    
    const card = document.createElement('div');
    card.className = 'canvas-card';
    card.dataset.widgetKey = widgetKey;
    card.style.left = layout.left + 'px';
    card.style.top = layout.top + 'px';
    card.style.width = layout.width + 'px';
    card.style.height = layout.minimized ? '40px' : layout.height + 'px';
    if (layout.minimized) card.classList.add('minimized');
    
    // Card Header
    const header = document.createElement('div');
    header.className = 'canvas-card-header';
    
    const title = document.createElement('div');
    title.className = 'canvas-card-title';
    title.textContent = widgetKey;
    header.appendChild(title);
    
    // Controls
    const controls = document.createElement('div');
    controls.className = 'canvas-card-controls';
    
    const minimizeBtn = document.createElement('button');
    minimizeBtn.className = 'canvas-card-btn';
    minimizeBtn.innerHTML = layout.minimized ? '🗖' : '🗕';
    minimizeBtn.title = layout.minimized ? 'Restaurar' : 'Minimizar';
    minimizeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isMin = card.classList.toggle('minimized');
      if (isMin) {
        card.style.height = '40px';
        minimizeBtn.innerHTML = '🗖';
        minimizeBtn.title = 'Restaurar';
      } else {
        card.style.height = (layout.height || 220) + 'px';
        minimizeBtn.innerHTML = '🗕';
        minimizeBtn.title = 'Minimizar';
      }
      this.saveSavedLayout();
    });
    controls.appendChild(minimizeBtn);
    
    const closeCardBtn = document.createElement('button');
    closeCardBtn.className = 'canvas-card-btn';
    closeCardBtn.innerHTML = '&times;';
    closeCardBtn.title = 'Desanclar del lienzo';
    closeCardBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      card.remove();
      _pinnedWidgetKeys.delete(widgetKey);
      this.saveSavedLayout();
      
      const event = new CustomEvent('widget-unpinned', { detail: { widgetKey } });
      document.dispatchEvent(event);
    });
    controls.appendChild(closeCardBtn);
    
    header.appendChild(controls);
    card.appendChild(header);
    
    // Card Body
    const body = document.createElement('div');
    body.className = 'canvas-card-body';
    
    // Build Iframe inside
    const widgetId = 'canvas-' + widgetKey;
    const persistedState = stateManager.getState(widgetKey) || {};
    const iframe = createIframe(body, widgetId, code); // Note: mounting iframe directly
    
    card.appendChild(body);
    
    // Resizer grip
    const resizer = document.createElement('div');
    resizer.className = 'canvas-card-resizer';
    card.appendChild(resizer);
    
    cardsContainer.appendChild(card);
    
    // Setup Drag-and-drop & Resizing listeners
    this.setupCardHandlers(card, header, resizer);
  },
  
  setupCardHandlers(card: HTMLElement, header: HTMLElement, resizer: HTMLElement): void {
    // Bring card to front on click
    card.addEventListener('mousedown', () => {
      _highestZIndex += 2;
      card.style.zIndex = String(_highestZIndex);
    });
    
    // Drag handlers
    header.addEventListener('mousedown', (e) => {
      if ((e.target as HTMLElement).closest('.canvas-card-btn')) return;
      e.preventDefault();
      
      card.classList.add('active-drag');
      const container = card.parentNode as HTMLElement;
      if (!container) return;
      
      let startX = e.clientX;
      let startY = e.clientY;
      let startLeft = card.offsetLeft;
      let startTop = card.offsetTop;
      
      function onMouseMove(ev: MouseEvent) {
        const dx = ev.clientX - startX;
        const dy = ev.clientY - startY;
        
        let l = startLeft + dx;
        let t = startTop + dy;
        
        // Boundaries
        l = Math.max(0, Math.min(l, container.clientWidth - card.clientWidth));
        t = Math.max(0, Math.min(t, container.clientHeight - card.clientHeight));
        
        card.style.left = l + 'px';
        card.style.top = t + 'px';
      }
      
      function onMouseUp() {
        card.classList.remove('active-drag');
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        CanvasWorkspace.saveSavedLayout();
      }
      
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    });
    
    // Resize handlers
    resizer.addEventListener('mousedown', (e) => {
      e.preventDefault();
      e.stopPropagation();
      
      let startX = e.clientX;
      let startY = e.clientY;
      let startW = card.clientWidth;
      let startH = card.clientHeight;
      
      function onMouseMove(ev: MouseEvent) {
        const dx = ev.clientX - startX;
        const dy = ev.clientY - startY;
        
        let w = startW + dx;
        let h = startH + dy;
        
        w = Math.max(200, w);
        if (!card.classList.contains('minimized')) {
          card.style.height = h + 'px';
        }
        card.style.width = w + 'px';
      }
      
      function onMouseUp() {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        CanvasWorkspace.saveSavedLayout();
      }
      
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    });
  },
  
  pinWidget(containerEl: HTMLElement, widgetKey: string, code: string): void {
    if (!widgetKey) return;
    
    const canvasEl = document.getElementById('canvas-workspace');
    const gutterEl = document.getElementById('canvas-gutter');
    const cardsContainer = document.getElementById('canvas-cards');
    if (!canvasEl || !cardsContainer) return;
    
    // 1. Open Canvas if closed
    if (canvasEl.classList.contains('collapsed')) {
      canvasEl.classList.remove('collapsed');
      gutterEl?.classList.remove('collapsed');
      document.getElementById('canvas-toggle')?.classList.add('active');
      localStorage.setItem(`canvas_collapsed_${_currentSessionId}`, 'false');
      const w = localStorage.getItem(`canvas_width_${_currentSessionId}`) || '400';
      canvasEl.style.width = w + 'px';
    }
    
    // 2. Play Fly-away animation
    const rect = containerEl.getBoundingClientRect();
    const clone = document.createElement('div');
    clone.className = 'fly-away-clone';
    clone.style.top = rect.top + 'px';
    clone.style.left = rect.left + 'px';
    clone.style.width = rect.width + 'px';
    clone.style.height = rect.height + 'px';
    clone.textContent = `Anclando ${widgetKey}...`;
    document.body.appendChild(clone);
    
    // Calculate final card index/offsets on canvas
    const index = document.querySelectorAll('#canvas-cards .canvas-card').length;
    const cardLayout: CardLayout = {
      left: 20 + (index % 5) * 30,
      top: 20 + Math.floor(index / 5) * 30,
      width: 300,
      height: 220,
      minimized: false
    };
    
    const targetRect = cardsContainer.getBoundingClientRect();
    const targetLeft = targetRect.left + cardLayout.left;
    const targetTop = targetRect.top + cardLayout.top;
    
    // Animate
    setTimeout(() => {
      clone.style.left = targetLeft + 'px';
      clone.style.top = targetTop + 'px';
      clone.style.width = cardLayout.width + 'px';
      clone.style.height = cardLayout.height + 'px';
      clone.style.opacity = '0.3';
    }, 50);
    
    clone.addEventListener('transitionend', () => {
      clone.remove();
      
      // 3. Render Card on Canvas
      this.addCardToCanvas(widgetKey, code, cardLayout);
      this.saveSavedLayout();
      
      // 4. Transform inline widget container into a link placeholder
      containerEl.textContent = '';
      const placeholder = document.createElement('a');
      placeholder.href = '#';
      placeholder.className = 'pinned-widget-placeholder';
      placeholder.dataset.widgetKey = widgetKey;
      placeholder.innerHTML = `<span class="pin-icon">📌</span> Widget anclado: <strong>${widgetKey}</strong> (Ver en Lienzo)`;
      placeholder.addEventListener('click', (e) => {
        e.preventDefault();
        const card = document.querySelector(`.canvas-card[data-widget-key="${widgetKey}"]`) as HTMLElement | null;
        if (card) {
          _highestZIndex += 2;
          card.style.zIndex = String(_highestZIndex);
          card.classList.add('active-drag');
          setTimeout(() => card.classList.remove('active-drag'), 800);
        }
      });
      containerEl.appendChild(placeholder);
    });
  },
  
  isPinned(widgetKey: string): boolean {
    return _pinnedWidgetKeys.has(widgetKey);
  }
};
