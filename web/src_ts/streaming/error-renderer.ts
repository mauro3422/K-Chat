import { C } from '../core/infra/DomContracts';
import { IDebugManager } from '../types/debug';
import type { StreamHandlerContext } from './ContentHandler';

interface ErrorPayload {
  type: string;
  message: string;
}

export class ErrorRenderer {
  constructor(
    private ensureBody: (ctx: StreamHandlerContext) => HTMLElement,
    private escHtml: (str: string) => string,
    private debug?: IDebugManager,
  ) {}

  handleError(data: string, ctx: StreamHandlerContext): void {
    this.debug?.logStream('error', data);

    let payload: ErrorPayload;
    try { payload = JSON.parse(data) as ErrorPayload; } catch { payload = { type: 'unknown', message: data }; }

    const errorType = payload.type || 'unknown';
    const errorMessage = payload.message || 'Error desconocido';

    const bodyEl = this.ensureBody(ctx);

    if (bodyEl.textContent === '✍️ Escribiendo...' || bodyEl.textContent === '✍️ Pensando...' || bodyEl.textContent === '') {
      bodyEl.textContent = '';
    }

    const errorCard = document.createElement('div');
    errorCard.className = C.ERROR_CARD;

    if (errorType === 'rate_limit') {
      errorCard.classList.add('rate-limit-card');
      errorCard.innerHTML = `
        <div class="${C.ERROR_HEADER} rate-limit-header">⏳ Modelo saturado</div>
        <div class="${C.ERROR_DETAIL}">${this.escHtml(errorMessage)}</div>
        <div class="${C.ERROR_HINT}">Límite del proveedor, reintentá en unos minutos.</div>
      `;
    } else {
      const userText = ctx.msgEl.dataset.userText || '';
      errorCard.innerHTML = `
        <div class="${C.ERROR_HEADER}">⚠ Respuesta interrumpida</div>
        <div class="${C.ERROR_DETAIL}">${this.escHtml(errorMessage)}</div>
        <button class="${C.RETRY_BTN}" data-user-text="${this.escHtml(userText)}">Reintentar envío</button>
      `;
    }

    bodyEl.appendChild(errorCard);
  }
}
