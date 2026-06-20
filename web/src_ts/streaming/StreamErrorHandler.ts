import { C } from '../core/infra/DomContracts';

export interface IStreamErrorPayload {
  type: string;
  message: string;
}

export interface IStreamErrorHandler {
  markPillAsError(pill: HTMLElement): void;
  markCallingPillsError(asstDiv: HTMLElement): void;
  showRetryMessage(asstDiv: HTMLElement, reason: string, errorType?: string): void;
  createStreamErrorHandler(): {
    handler: (event: string, data: string) => void;
    getError: () => IStreamErrorPayload | null;
    clearError: () => void;
  };
}

function clearElement(el: HTMLElement): void {
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
}

function escHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function markPillAsError(pill: HTMLElement): void {
  pill.className = C.TC_ITEM_ERROR;
  const toolName = pill.getAttribute('data-tool') || 'tool';
  pill.textContent = `✗ ${toolName}`;
  window.dispatchEvent(new CustomEvent('kairos:ui-log', {
    detail: { label: 'tool_error', detail: toolName },
  }));
}

function markCallingPillsError(asstDiv: HTMLElement): void {
  asstDiv.querySelectorAll(`.${C.TC_ITEM}.calling`).forEach((pill) => {
    markPillAsError(pill as HTMLElement);
  });
}

function showRetryMessage(asstDiv: HTMLElement, reason: string, errorType?: string): void {
  const bodyDiv = asstDiv.querySelector(`.${C.MSG_BODY}`) as HTMLElement | null;
  if (!bodyDiv) return;

  clearElement(bodyDiv);
  const card = document.createElement('div');
  card.className = C.ERROR_CARD;

  if (errorType === 'rate_limit') {
    card.classList.add('rate-limit-card');

    const header = document.createElement('div');
    header.className = 'error-header rate-limit-header';
    header.textContent = '⏳ Modelo saturado';

    const detail = document.createElement('div');
    detail.className = 'error-detail';
    detail.textContent = reason;

    const hint = document.createElement('div');
    hint.className = 'error-hint';
    hint.textContent = 'Es un límite del proveedor, no de K-Chat. Podés intentar de nuevo en unos minutos.';

    card.appendChild(header);
    card.appendChild(detail);
    card.appendChild(hint);
  } else {
    const header = document.createElement('div');
    header.className = 'error-header';
    header.textContent = '⚠ Respuesta interrumpida';

    const detail = document.createElement('div');
    detail.className = 'error-detail';
    detail.textContent = reason;

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'error-retry-btn';
    button.textContent = 'Reintentar envío';

    card.appendChild(header);
    card.appendChild(detail);
    card.appendChild(button);
  }

  bodyDiv.appendChild(card);
}

function createStreamErrorHandler() {
  let streamError: IStreamErrorPayload | null = null;
  return {
    handler: (event: string, data: string) => {
      if (event !== 'error') return;
      try {
        const parsed = JSON.parse(data) as Partial<IStreamErrorPayload>;
        streamError = {
          type: parsed.type || 'unknown',
          message: parsed.message || 'Error desconocido',
        };
      } catch {
        streamError = { type: 'unknown', message: data };
      }
    },
    getError: () => streamError,
    clearError: () => {
      streamError = null;
    },
  };
}

export const StreamErrorHandler: IStreamErrorHandler = {
  markPillAsError,
  markCallingPillsError,
  showRetryMessage,
  createStreamErrorHandler,
};
