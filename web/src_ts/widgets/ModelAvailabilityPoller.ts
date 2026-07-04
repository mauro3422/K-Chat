import { getLogger } from '../core/infra/LoggerFactory';
import type { ILogger } from '../core/infra/Logger';

interface ModelAvailabilityEntry {
  status: 'available' | 'rate_limited' | 'unavailable' | 'unknown';
  cooldown_remaining?: number;
}

interface ModelAvailabilityPayload {
  models?: Record<string, ModelAvailabilityEntry>;
  limited_count?: number;
  go_quota_exhausted?: boolean;
}

const POLL_INTERVAL_MS = 60_000;
const POLL_INTERVAL_ERROR_MS = 120_000;

/**
 * Polls ``/models/availability`` every minute and updates the UI:
 *
 * - Inserts a small ``rl-badge`` next to ``#model-select-wrapper`` when
 *   some models are rate-limited.
 * - Toggles a top banner when the Go plan quota is exhausted.
 *
 * Replaces the legacy ``model-availability.js`` IIFE. The dropped
 * responsibility is the per-``<option>`` emoji decoration of the hidden
 * ``<select>`` — that widget is now invisible because the TS ModelSelector
 * renders an interactive dropdown via divs; its cooldown badge is fed by
 * template-time metadata instead.
 */
export class ModelAvailabilityPoller {
  private logger: ILogger;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private badge: HTMLElement | null = null;
  private banner: HTMLElement | null = null;

  constructor() {
    this.logger = getLogger('model-availability');
  }

  init(): void {
    if (!('fetch' in window)) return;
    void this.tick();
  }

  private async tick(): Promise<void> {
    try {
      const res = await fetch('/models/availability');
      if (!res.ok) {
        this.schedule(POLL_INTERVAL_ERROR_MS);
        return;
      }
      const data = (await res.json()) as ModelAvailabilityPayload;
      this.updateLimitedBadge(data);
      this.updateQuotaBanner(data);
      this.schedule(POLL_INTERVAL_MS);
    } catch (e) {
      this.logger.warn('poll_failed', String(e));
      this.schedule(POLL_INTERVAL_ERROR_MS);
    }
  }

  private schedule(intervalMs: number): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.tick(), intervalMs);
  }

  private updateLimitedBadge(data: ModelAvailabilityPayload): void {
    const limited = data.limited_count || 0;
    const selectWrapper = document.getElementById('model-select-wrapper');
    if (limited > 0 && selectWrapper) {
      if (!this.badge || !document.getElementById('rl-badge')) {
        this.badge = document.createElement('span');
        this.badge.id = 'rl-badge';
        this.badge.title = `${limited} modelo(s) saturado(s) — esperá al countdown`;
        this.badge.ariaLabel = `${limited} modelo(s) con límite de tasa`;
        this.badge.role = 'status';
        this.badge.style.cssText =
          'position:absolute;top:-6px;right:-6px;font-size:9px;background:var(--accent-red);color:#fff;border-radius:50%;width:16px;height:16px;display:flex;align-items:center;justify-content:center;line-height:1;cursor:help;animation:rl-badge-pulse 2s ease-in-out infinite;';
        // Add keyframe animation
        if (!document.getElementById('rl-badge-style')) {
          const style = document.createElement('style');
          style.id = 'rl-badge-style';
          style.textContent = `@keyframes rl-badge-pulse { 0%,100% { opacity:1; } 50% { opacity:0.6; } }`;
          document.head.appendChild(style);
        }
        selectWrapper.appendChild(this.badge);
      }
      this.badge.textContent = String(limited);
      // Click on badge: show model names from the payload
      this.badge.onclick = () => {
        const names = data.models
          ? Object.entries(data.models)
              .filter(([_, entry]) => entry.status === 'rate_limited')
              .map(([name]) => name)
          : [];
        if (names.length > 0) {
          this.badge!.title = names.join(', ');
        }
      };
    } else if (this.badge) {
      this.badge.remove();
      this.badge = null;
    }
  }

  private updateQuotaBanner(data: ModelAvailabilityPayload): void {
    if (!data.go_quota_exhausted) {
      this.banner?.remove();
      this.banner = null;
      return;
    }
    if (this.banner && document.getElementById('go-quota-warning')) return;
    const select = document.getElementById('model-select');
    const header = document.querySelector('.chat-header') || select?.parentNode;
    if (!header || !header.parentNode) return;
    this.banner = document.createElement('div');
    this.banner.id = 'go-quota-warning';
    this.banner.textContent = '⚠️ Go plan quota agotada — los modelos Go no funcionarán hasta que recargues';
    this.banner.style.cssText =
      'background:var(--accent-red);color:#fff;padding:6px 12px;font-size:13px;text-align:center;border-radius:6px;margin-bottom:8px;';
    header.parentNode.insertBefore(this.banner, header);
  }

  dispose(): void {
    if (this.timer) clearTimeout(this.timer);
    this.badge?.remove();
    this.banner?.remove();
  }
}