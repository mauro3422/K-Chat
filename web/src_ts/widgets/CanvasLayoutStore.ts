import { CardLayout, ILayoutStore } from '../types/widgets';

export class CanvasLayoutStore implements ILayoutStore {
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
        (c: unknown): c is CardLayout =>
          typeof c === 'object' && c !== null &&
          typeof (c as Record<string, unknown>).key === 'string' &&
          typeof (c as Record<string, unknown>).code === 'string'
      );
    } catch {
      return [];
    }
  }

  clear(sessionId: string): void {
    localStorage.removeItem(this.storagePrefix + sessionId);
  }
}
