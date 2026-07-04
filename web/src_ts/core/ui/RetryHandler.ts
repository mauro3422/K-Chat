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
  private _retryTimer: ReturnType<typeof setTimeout> | null = null;

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

    // Stop the pulsing animation on the failed message
    assistantEl.classList.remove('streaming', 'live-msg');

    // Clean up reasoning/tool-calls from the failed attempt, but preserve memory bubble
    assistantEl.querySelectorAll('.reasoning:not(.memories-phase), .tool-calls').forEach(el => el.remove());

    // Replace body with a retry indicator instead of removing the message
    const body = assistantEl.querySelector('.msg-body');
    if (body) {
      body.innerHTML = `<p style="color:#e6a817;font-style:italic;padding:8px 12px;margin:0;">
        🔄 Error del provider — reintentando (${this.count}/${this.maxRetries})...
      </p>`;
    }

    // Keep the message in the DOM — don't remove it.
    // The retry will create a new message via handleChatSend → beginStreaming.

    // Cancel any previous pending retry before scheduling a new one
    this._cancelPendingRetry();

    const delay = 2000 * this.count;
    this._retryTimer = setTimeout(() => {
      this._retryTimer = null;
      onRetry();
    }, delay);
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
