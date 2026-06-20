import { IEventBus } from '../../types/events';
import { IFileUploader } from './FileUploader';
import { IChatForm } from '../../types/chat-form';
import { getLogger } from '../infra/LoggerFactory';
import { ILogger } from '../infra/Logger';

export class ChatForm implements IChatForm {
  private logger: ILogger = getLogger('chat-form');
  private formEl: HTMLFormElement | null = null;
  private inputEl: HTMLTextAreaElement | null = null;
  private eventBus: IEventBus;
  private fileUploader: IFileUploader;
  private isStreaming = false;
  private isRateLimited = false;

  constructor(eventBus: IEventBus, fileUploader: IFileUploader) {
    this.eventBus = eventBus;
    this.fileUploader = fileUploader;
  }

  init(): void {
    this.formEl = document.getElementById('chat-form') as HTMLFormElement;
    this.inputEl = document.getElementById('msg-input') as HTMLTextAreaElement;

    if (!this.formEl || !this.inputEl) {
      console.warn('ChatForm elements not found in DOM.');
      return;
    }

    this.formEl.addEventListener('submit', (e) => {
      e.preventDefault();
      this.handleSubmit();
    });

    this.inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.handleSubmit();
      }
      if (e.key === 'Escape' && this.isStreaming) {
        this.eventBus.emit('stream:abort', {});
      }
    });

    this.eventBus.on<{ duration: number; remainingSec: number }>('rate-limit:started', (data) => {
      this.onRateLimitStarted(data.remainingSec);
    });

    this.eventBus.on<{ remainingSec: number }>('rate-limit:tick', (data) => {
      this.updateRateLimitButton(data.remainingSec);
    });

    this.eventBus.on('rate-limit:expired', () => {
      this.onRateLimitExpired();
    });

    this.restoreModelSelection();

    const modelSelect = document.getElementById('model-select') as HTMLSelectElement | null;
    if (modelSelect) {
      modelSelect.addEventListener('change', () => {
        try {
          localStorage.setItem('selected_model', modelSelect.value);
        } catch { /* localStorage unavailable */ }
      });
    }
  }

  private restoreModelSelection(): void {
    const modelSelect = document.getElementById('model-select') as HTMLSelectElement | null;
    if (!modelSelect) return;
    try {
      const saved = localStorage.getItem('selected_model');
      if (saved && Array.from(modelSelect.options).some(o => o.value === saved)) {
        modelSelect.value = saved;
      }
    } catch { /* localStorage unavailable */ }
  }

  private getSelectedModel(): string {
    // Read from ModelSelector's global reference (set by ModelSelector on change)
    const fromGlobal = (window as any).__k?.selectedModel;
    if (fromGlobal) return fromGlobal;
    // Fallback: localStorage (ModelSelector persists there)
    const saved = localStorage.getItem('selected_model');
    if (saved) return saved;
    // Last resort: hidden select (may be empty if no options)
    const modelSelect = document.getElementById('model-select') as HTMLSelectElement | null;
    if (modelSelect && modelSelect.value) return modelSelect.value;
    return 'default';
  }

  private handleSubmit(): void {
    if (!this.inputEl) return;

    if (this.isRateLimited) return;

    if (this.isStreaming) {
      this.eventBus.emit('stream:abort', {});
      return;
    }

    const text = this.inputEl.value.trim();
    if (!text && !this.fileUploader.hasFiles()) return;

    const files = this.fileUploader.getFiles();
    const model = this.getSelectedModel();
    this.inputEl.value = '';
    this.fileUploader.clear();
    this.logger.info('submit', { textLen: text.length, filesCount: files?.length || 0, model });
    this.eventBus.emit('chat:send', { text, files, model });
  }

  private onRateLimitStarted(remainingSec: number): void {
    this.isRateLimited = true;
    if (this.inputEl) {
      this.inputEl.disabled = true;
      this.inputEl.placeholder = '⏳ Rate limit activo — esperá al countdown...';
    }
    this.updateRateLimitButton(remainingSec);
  }

  private onRateLimitExpired(): void {
    this.isRateLimited = false;
    if (this.inputEl) {
      this.inputEl.disabled = false;
      this.inputEl.placeholder = 'Escribe un mensaje...';
    }
    this.restoreSubmitButton();
  }

  private updateRateLimitButton(remainingSec: number): void {
    const submitBtn = document.getElementById('chat-submit-btn') as HTMLButtonElement;
    if (!submitBtn) return;
    submitBtn.disabled = true;
    submitBtn.innerHTML = `<span style="font-size:14px;font-weight:600">${remainingSec}s</span>`;
    submitBtn.style.background = '#f85149';
    submitBtn.style.border = 'none';
  }

  private restoreSubmitButton(): void {
    const submitBtn = document.getElementById('chat-submit-btn') as HTMLButtonElement;
    if (!submitBtn) return;
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<svg class="send-svg" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
      <line x1="22" y1="2" x2="11" y2="13"></line>
      <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
    </svg>`;
    submitBtn.style.background = '';
    submitBtn.style.border = '';
  }

  setStreamingState(isStreaming: boolean): void {
    this.isStreaming = isStreaming;
    if (this.isRateLimited) return;
    const submitBtn = document.getElementById('chat-submit-btn') as HTMLButtonElement;
    if (submitBtn) {
      if (isStreaming) {
        submitBtn.innerHTML = `<svg viewBox="0 0 24 24" width="18" height="18" style="display:block">
          <circle cx="12" cy="12" r="11" fill="#ff3333"/>
          <rect x="7" y="7" width="10" height="10" rx="2" fill="white"/>
        </svg>`;
        submitBtn.style.background = 'transparent';
        submitBtn.style.border = '2px solid #ff3333';
      } else {
        submitBtn.innerHTML = `<svg class="send-svg" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
          <line x1="22" y1="2" x2="11" y2="13"></line>
          <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
        </svg>`;
        submitBtn.style.background = '';
        submitBtn.style.border = '';
      }
    }
    const inputContainer = document.querySelector('.chat-input-container') as HTMLElement;
    if (inputContainer) {
      inputContainer.classList.toggle('streaming', isStreaming);
    }
  }
}
