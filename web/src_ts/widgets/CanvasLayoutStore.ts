export interface CardLayout {
  key: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minimized: boolean;
  code: string;
}

export class CanvasLayoutStore {
  private storagePrefix = 'canvas-layout-v2-';

  saveLayout(sessionId: string, cards: CardLayout[]): void {
    try {
      localStorage.setItem(this.storagePrefix + sessionId, JSON.stringify(cards));
    } catch {
      // localStorage might be full
    }
  }

  loadLayout(sessionId: string): CardLayout[] {
    try {
      const data = localStorage.getItem(this.storagePrefix + sessionId);
      if (!data) return [];
      const parsed = JSON.parse(data);
      if (!Array.isArray(parsed)) return [];
      return parsed.filter(
        (c: any): c is CardLayout =>
          typeof c.key === 'string' && typeof c.code === 'string'
      );
    } catch {
      return [];
    }
  }

  clear(sessionId: string): void {
    localStorage.removeItem(this.storagePrefix + sessionId);
  }
}
