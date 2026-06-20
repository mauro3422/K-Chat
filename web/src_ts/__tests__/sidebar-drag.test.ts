import { describe, it, expect, beforeEach, afterEach } from 'vitest';

type SidebarState = {
  isDragging: boolean;
  sidebarEl: HTMLElement | null;
  gutterEl: HTMLElement | null;
  MIN_SIDEBAR_WIDTH: number;
  MAX_SIDEBAR_WIDTH: number;
};

function setupSidebarElements() {
  const sidebar = document.createElement('div');
  sidebar.id = 'sidebar';
  const toggle = document.createElement('button');
  toggle.id = 'sidebar-toggle';
  const gutter = document.createElement('div');
  gutter.id = 'sidebar-gutter';
  document.body.appendChild(sidebar);
  document.body.appendChild(toggle);
  document.body.appendChild(gutter);
  return { sidebar, toggle, gutter };
}

function setupSidebarToggle(sidebar: HTMLElement, toggle: HTMLElement) {
  toggle.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
    toggle.textContent = sidebar.classList.contains('collapsed') ? '\u25B6' : '\u25C0';
    toggle.title = sidebar.classList.contains('collapsed') ? 'Mostrar panel' : 'Ocultar panel';
  });
}

function setupGutterDrag(state: SidebarState) {
  const { sidebarEl, gutterEl } = state;

  function onGutterDown(e: MouseEvent) {
    if (sidebarEl?.classList.contains('collapsed')) return;
    state.isDragging = true;
    gutterEl?.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  }

  function onGutterMove(e: MouseEvent) {
    if (!state.isDragging || !sidebarEl) return;
    const newWidth = Math.min(state.MAX_SIDEBAR_WIDTH, Math.max(state.MIN_SIDEBAR_WIDTH, e.clientX));
    sidebarEl.style.width = newWidth + 'px';
    localStorage.setItem('sidebar_width', String(newWidth));
  }

  function onGutterUp() {
    if (!state.isDragging) return;
    state.isDragging = false;
    gutterEl?.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }

  if (gutterEl) {
    gutterEl.addEventListener('mousedown', onGutterDown);
  }
  document.addEventListener('mousemove', onGutterMove);
  document.addEventListener('mouseup', onGutterUp);

  return { onGutterDown, onGutterMove, onGutterUp };
}

describe('anti-regression: sidebar toggle & gutter drag', () => {
  let sidebar: HTMLElement;
  let toggle: HTMLElement;
  let gutter: HTMLElement;

  beforeEach(() => {
    const els = setupSidebarElements();
    sidebar = els.sidebar;
    toggle = els.toggle;
    gutter = els.gutter;
  });

  afterEach(() => {
    document.body.innerHTML = '';
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    localStorage.clear();
  });

  describe('sidebar toggle click', () => {
    it('toggles collapsed class on #sidebar', () => {
      setupSidebarToggle(sidebar, toggle);
      expect(sidebar.classList.contains('collapsed')).toBe(false);
      toggle.click();
      expect(sidebar.classList.contains('collapsed')).toBe(true);
      toggle.click();
      expect(sidebar.classList.contains('collapsed')).toBe(false);
    });

    it('changes toggle text between ▶ and ◀', () => {
      setupSidebarToggle(sidebar, toggle);
      expect(toggle.textContent).toBe('');
      toggle.click();
      expect(toggle.textContent).toBe('\u25B6');
      toggle.click();
      expect(toggle.textContent).toBe('\u25C0');
    });

    it('changes toggle title between Mostrar panel and Ocultar panel', () => {
      setupSidebarToggle(sidebar, toggle);
      toggle.click();
      expect(toggle.title).toBe('Mostrar panel');
      toggle.click();
      expect(toggle.title).toBe('Ocultar panel');
    });
  });

  describe('sidebar collapse persistence', () => {
    it('does not save to localStorage when collapsed', () => {
      const state: SidebarState = { isDragging: false, sidebarEl: sidebar, gutterEl: gutter, MIN_SIDEBAR_WIDTH: 160, MAX_SIDEBAR_WIDTH: 500 };
      setupGutterDrag(state);
      sidebar.classList.add('collapsed');
      gutter.dispatchEvent(new MouseEvent('mousedown', { clientX: 300 }));
      expect(state.isDragging).toBe(false);
      expect(localStorage.getItem('sidebar_width')).toBeNull();
    });
  });

  describe('gutter mousedown', () => {
    it('adds dragging class to gutter', () => {
      const state: SidebarState = { isDragging: false, sidebarEl: sidebar, gutterEl: gutter, MIN_SIDEBAR_WIDTH: 160, MAX_SIDEBAR_WIDTH: 500 };
      setupGutterDrag(state);
      gutter.dispatchEvent(new MouseEvent('mousedown', { clientX: 300 }));
      expect(gutter.classList.contains('dragging')).toBe(true);
    });

    it('sets body cursor to col-resize', () => {
      const state: SidebarState = { isDragging: false, sidebarEl: sidebar, gutterEl: gutter, MIN_SIDEBAR_WIDTH: 160, MAX_SIDEBAR_WIDTH: 500 };
      setupGutterDrag(state);
      gutter.dispatchEvent(new MouseEvent('mousedown', { clientX: 300 }));
      expect(document.body.style.cursor).toBe('col-resize');
    });

    it('sets body userSelect to none', () => {
      const state: SidebarState = { isDragging: false, sidebarEl: sidebar, gutterEl: gutter, MIN_SIDEBAR_WIDTH: 160, MAX_SIDEBAR_WIDTH: 500 };
      setupGutterDrag(state);
      gutter.dispatchEvent(new MouseEvent('mousedown', { clientX: 300 }));
      expect(document.body.style.userSelect).toBe('none');
    });
  });

  describe('gutter mousemove during drag', () => {
    it('updates sidebar width based on clientX', () => {
      const state: SidebarState = { isDragging: false, sidebarEl: sidebar, gutterEl: gutter, MIN_SIDEBAR_WIDTH: 160, MAX_SIDEBAR_WIDTH: 500 };
      setupGutterDrag(state);
      gutter.dispatchEvent(new MouseEvent('mousedown', { clientX: 300 }));
      document.dispatchEvent(new MouseEvent('mousemove', { clientX: 250 }));
      expect(sidebar.style.width).toBe('250px');
    });

    it('clamps to MIN_SIDEBAR_WIDTH when clientX too small', () => {
      const state: SidebarState = { isDragging: false, sidebarEl: sidebar, gutterEl: gutter, MIN_SIDEBAR_WIDTH: 160, MAX_SIDEBAR_WIDTH: 500 };
      setupGutterDrag(state);
      gutter.dispatchEvent(new MouseEvent('mousedown', { clientX: 100 }));
      document.dispatchEvent(new MouseEvent('mousemove', { clientX: 50 }));
      expect(sidebar.style.width).toBe('160px');
    });

    it('clamps to MAX_SIDEBAR_WIDTH when clientX too large', () => {
      const state: SidebarState = { isDragging: false, sidebarEl: sidebar, gutterEl: gutter, MIN_SIDEBAR_WIDTH: 160, MAX_SIDEBAR_WIDTH: 500 };
      setupGutterDrag(state);
      gutter.dispatchEvent(new MouseEvent('mousedown', { clientX: 100 }));
      document.dispatchEvent(new MouseEvent('mousemove', { clientX: 600 }));
      expect(sidebar.style.width).toBe('500px');
    });

    it('writes sidebar_width to localStorage', () => {
      const state: SidebarState = { isDragging: false, sidebarEl: sidebar, gutterEl: gutter, MIN_SIDEBAR_WIDTH: 160, MAX_SIDEBAR_WIDTH: 500 };
      setupGutterDrag(state);
      gutter.dispatchEvent(new MouseEvent('mousedown', { clientX: 300 }));
      document.dispatchEvent(new MouseEvent('mousemove', { clientX: 280 }));
      expect(localStorage.getItem('sidebar_width')).toBe('280');
    });
  });

  describe('gutter mouseup', () => {
    it('sets isDragging to false', () => {
      const state: SidebarState = { isDragging: false, sidebarEl: sidebar, gutterEl: gutter, MIN_SIDEBAR_WIDTH: 160, MAX_SIDEBAR_WIDTH: 500 };
      setupGutterDrag(state);
      gutter.dispatchEvent(new MouseEvent('mousedown', { clientX: 300 }));
      expect(state.isDragging).toBe(true);
      document.dispatchEvent(new MouseEvent('mouseup'));
      expect(state.isDragging).toBe(false);
    });

    it('removes dragging class from gutter', () => {
      const state: SidebarState = { isDragging: false, sidebarEl: sidebar, gutterEl: gutter, MIN_SIDEBAR_WIDTH: 160, MAX_SIDEBAR_WIDTH: 500 };
      setupGutterDrag(state);
      gutter.dispatchEvent(new MouseEvent('mousedown', { clientX: 300 }));
      expect(gutter.classList.contains('dragging')).toBe(true);
      document.dispatchEvent(new MouseEvent('mouseup'));
      expect(gutter.classList.contains('dragging')).toBe(false);
    });

    it('resets body cursor and userSelect', () => {
      const state: SidebarState = { isDragging: false, sidebarEl: sidebar, gutterEl: gutter, MIN_SIDEBAR_WIDTH: 160, MAX_SIDEBAR_WIDTH: 500 };
      setupGutterDrag(state);
      gutter.dispatchEvent(new MouseEvent('mousedown', { clientX: 300 }));
      document.dispatchEvent(new MouseEvent('mouseup'));
      expect(document.body.style.cursor).toBe('');
      expect(document.body.style.userSelect).toBe('');
    });
  });

  describe('gutter ignored when collapsed', () => {
    it('does not start dragging when sidebar has collapsed class', () => {
      const state: SidebarState = { isDragging: false, sidebarEl: sidebar, gutterEl: gutter, MIN_SIDEBAR_WIDTH: 160, MAX_SIDEBAR_WIDTH: 500 };
      setupGutterDrag(state);
      sidebar.classList.add('collapsed');
      gutter.dispatchEvent(new MouseEvent('mousedown', { clientX: 300 }));
      expect(state.isDragging).toBe(false);
      expect(gutter.classList.contains('dragging')).toBe(false);
    });
  });

  describe('edge case - no gutter', () => {
    it('does not throw errors when #sidebar-gutter does not exist', () => {
      document.body.removeChild(gutter);
      const state: SidebarState = { isDragging: false, sidebarEl: sidebar, gutterEl: null, MIN_SIDEBAR_WIDTH: 160, MAX_SIDEBAR_WIDTH: 500 };
      expect(() => {
        setupGutterDrag(state);
        document.dispatchEvent(new MouseEvent('mousemove', { clientX: 200 }));
        document.dispatchEvent(new MouseEvent('mouseup'));
      }).not.toThrow();
    });

    it('does not throw when both sidebar and gutter are missing', () => {
      document.body.innerHTML = '';
      const state: SidebarState = { isDragging: false, sidebarEl: null, gutterEl: null, MIN_SIDEBAR_WIDTH: 160, MAX_SIDEBAR_WIDTH: 500 };
      expect(() => {
        setupGutterDrag(state);
        document.dispatchEvent(new MouseEvent('mousemove', { clientX: 200 }));
        document.dispatchEvent(new MouseEvent('mouseup'));
      }).not.toThrow();
    });
  });
});
