import { IEventBus } from '../../types/events';
import { getLogger } from '../infra/LoggerFactory';
import { ILogger } from '../infra/Logger';

export interface IRateLimitCooldown {
  readonly isActive: boolean;
  readonly remainingSec: number;
  start(durationMs?: number): void;
  cancel(): void;
  canSubmit(): boolean;
}

const DEFAULT_COOLDOWN_MS = 60000;

export class RateLimitCooldown implements IRateLimitCooldown {
  private eventBus: IEventBus;
  private logger: ILogger = getLogger('rate-limit');
  private _isActive = false;
  private _endTime = 0;
  private _tickTimer: ReturnType<typeof setInterval> | null = null;
  private _expireTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(eventBus: IEventBus) {
    this.eventBus = eventBus;
  }

  get isActive(): boolean {
    return this._isActive && Date.now() < this._endTime;
  }

  get remainingSec(): number {
    if (!this.isActive) return 0;
    return Math.ceil((this._endTime - Date.now()) / 1000);
  }

  start(durationMs: number = DEFAULT_COOLDOWN_MS): void {
    this.cancel();

    this._isActive = true;
    this._endTime = Date.now() + durationMs;

    const remainingSec = this.remainingSec;
    this.logger.warn('start', `duration=${durationMs}ms remaining=${remainingSec}s`);
    this.eventBus.emit('rate-limit:started', { duration: durationMs, remainingSec });

    this._expireTimer = setTimeout(() => {
      this.expire();
    }, durationMs);

    this.startTicks();
  }

  cancel(): void {
    this.stopTicks();
    if (this._expireTimer) {
      clearTimeout(this._expireTimer);
      this._expireTimer = null;
    }
    this._isActive = false;
    this._endTime = 0;
    this.logger.info('cancel');
  }

  canSubmit(): boolean {
    return !this.isActive;
  }

  private expire(): void {
    this.stopTicks();
    this._isActive = false;
    this._endTime = 0;
    this.eventBus.emit('rate-limit:expired', {});
    this.logger.info('expire');
  }

  private startTicks(): void {
    this.stopTicks();
    this._tickTimer = setInterval(() => {
      if (!this.isActive) {
        this.expire();
        return;
      }
      const sec = this.remainingSec;
      this.logger.debug('tick', `remaining=${sec}s`);
      this.eventBus.emit('rate-limit:tick', { remainingSec: sec });
    }, 1000);
  }

  private stopTicks(): void {
    if (this._tickTimer) {
      clearInterval(this._tickTimer);
      this._tickTimer = null;
    }
  }
}
