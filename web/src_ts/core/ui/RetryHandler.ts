import { IDebugManager } from '../../types/debug';

export type RetryCheckpointState = 'waiting' | 'active' | 'completed' | 'failed';

export function createRetryCheckpointElement(options: {
  attempt: number;
  maxRetries: number;
  reason: string;
  state: RetryCheckpointState;
}): HTMLElement {
  const { attempt, maxRetries, reason, state } = options;
  const statusLabels: Record<RetryCheckpointState, string> = {
    waiting: 'Preparando reintento',
    active: 'Continuando desde la última fase confirmada',
    completed: 'Reanudación completada',
    failed: 'Intento interrumpido',
  };
  const card = document.createElement('section');
  card.className = `retry-checkpoint retry-checkpoint--${state}`;
  card.dataset.retryAttempt = String(attempt);
  card.setAttribute('role', 'status');
  card.setAttribute('aria-live', 'polite');

  const header = document.createElement('div');
  header.className = 'retry-checkpoint__header';
  const title = document.createElement('strong');
  title.textContent = '↻ Reanudación desde checkpoint';
  const badge = document.createElement('span');
  badge.className = 'retry-checkpoint__badge';
  badge.textContent = `Intento ${attempt}/${maxRetries}`;
  header.append(title, badge);

  const status = document.createElement('span');
  status.className = 'retry-checkpoint__status';
  status.textContent = statusLabels[state];
  const detail = document.createElement('small');
  detail.className = 'retry-checkpoint__detail';
  detail.textContent = reason || 'El stream se interrumpió';
  card.append(header, status, detail);
  return card;
}

export interface IRetryController {
  readonly count: number;
  readonly maxRetries: number;
  shouldRetry(hasContent: boolean): boolean;
  getStreamTimeout(): number;
  scheduleRetry(options: {
    assistantEl: HTMLElement;
    userText: string;
    reason: string;
    onRetry: (attempt: number) => void;
  }): void;
  showRetryCheckpoint(options: {
    assistantEl: HTMLElement;
    attempt: number;
    maxRetries?: number;
    reason: string;
    state: RetryCheckpointState;
  }): void;
  markRetryStarted(assistantEl: HTMLElement, attempt: number): void;
  markRetryCompleted(assistantEl: HTMLElement): void;
  resetRetryCount(): void;
}

export class RetryController implements IRetryController {
  count = 0;
  maxRetries = 3;
  streamTimeout: number | null = null;
  private _retryTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private debug?: IDebugManager) {}

  shouldRetry(hasContent: boolean): boolean {
    return this.count < this.maxRetries && !hasContent;
  }

  getStreamTimeout(): number {
    return this.streamTimeout || 300000;
  }

  scheduleRetry({ assistantEl, reason, onRetry }: {
    assistantEl: HTMLElement;
    userText: string;
    reason: string;
    onRetry: (attempt: number) => void;
  }): void {
    this.count++;
    const attempt = this.count;
    this.debug?.logUI('retry', `Retry ${attempt}/${this.maxRetries}: ${reason}`);
    assistantEl.classList.remove('streaming', 'live-msg');

    this.showRetryCheckpoint({
      assistantEl,
      attempt,
      reason,
      state: 'waiting',
    });

    this._cancelPendingRetry();
    const delay = 2000 * attempt;
    this._retryTimer = setTimeout(() => {
      this._retryTimer = null;
      onRetry(attempt);
    }, delay);
  }

  showRetryCheckpoint({ assistantEl, attempt, maxRetries, reason, state }: {
    assistantEl: HTMLElement;
    attempt: number;
    maxRetries?: number;
    reason: string;
    state: RetryCheckpointState;
  }): void {
    const previous = assistantEl.querySelector(
      '.retry-checkpoint--active, .retry-checkpoint--waiting',
    ) as HTMLElement | null;
    if (previous) {
      previous.classList.remove('retry-checkpoint--active', 'retry-checkpoint--waiting');
      previous.classList.add('retry-checkpoint--failed');
      const previousStatus = previous.querySelector('.retry-checkpoint__status');
      if (previousStatus) previousStatus.textContent = 'Intento interrumpido';
    }

    assistantEl.appendChild(createRetryCheckpointElement({
      attempt,
      maxRetries: maxRetries ?? this.maxRetries,
      reason,
      state,
    }));
  }

  markRetryStarted(assistantEl: HTMLElement, attempt: number): void {
    const card = assistantEl.querySelector(
      `.retry-checkpoint[data-retry-attempt="${attempt}"]`,
    ) as HTMLElement | null;
    if (!card) return;
    card.classList.remove('retry-checkpoint--waiting');
    card.classList.add('retry-checkpoint--active');
    const status = card.querySelector('.retry-checkpoint__status');
    if (status) status.textContent = 'Continuando desde la última fase confirmada';
  }

  markRetryCompleted(assistantEl: HTMLElement): void {
    const cards = assistantEl.querySelectorAll('.retry-checkpoint--active');
    const card = cards[cards.length - 1] as HTMLElement | undefined;
    if (!card) return;
    card.classList.remove('retry-checkpoint--active');
    card.classList.add('retry-checkpoint--completed');
    const status = card.querySelector('.retry-checkpoint__status');
    if (status) status.textContent = 'Reanudación completada';
  }

  resetRetryCount(): void {
    this.count = 0;
    this._cancelPendingRetry();
  }

  private _cancelPendingRetry(): void {
    if (this._retryTimer !== null) {
      clearTimeout(this._retryTimer);
      this._retryTimer = null;
    }
  }
}
