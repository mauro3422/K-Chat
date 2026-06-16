import { IDebugManager } from '../../types/debug';

export interface IRetryController {
  readonly count: number;
  readonly maxRetries: number;
  shouldRetry(hasContent: boolean): boolean;
  getStreamTimeout(): number;
  scheduleRetry(options: {
    assistantEl: HTMLElement;
    userText: string;
    reason: string;
    onRetry: () => void;
  }): void;
  resetRetryCount(): void;
}

export class RetryController implements IRetryController {
  count = 0;
  maxRetries = 3;
  streamTimeout: number | null = null;

  constructor(private debug?: IDebugManager) {}

  shouldRetry(hasContent: boolean): boolean {
    return this.count < this.maxRetries && !hasContent;
  }

  getStreamTimeout(): number {
    return this.streamTimeout || 120000;
  }

  scheduleRetry({ assistantEl, userText, reason, onRetry }: {
    assistantEl: HTMLElement;
    userText: string;
    reason: string;
    onRetry: () => void;
  }): void {
    this.count++;
    this.debug?.logUI('retry', `Retry ${this.count}/${this.maxRetries}: ${reason}`);

    assistantEl.querySelectorAll('.reasoning, .tool-calls').forEach(el => el.remove());

    const body = assistantEl.querySelector('.msg-body');
    if (body) body.innerHTML = '';

    assistantEl.remove();

    const delay = 2000 * this.count;
    setTimeout(onRetry, delay);
  }

  resetRetryCount(): void {
    this.count = 0;
  }
}
