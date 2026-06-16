import { C } from '../core/DomContracts';
import { IDebugManager } from '../types/debug';
import { getLogger } from '../core/LoggerFactory';
import { ILogger } from '../core/Logger';
import type { StreamHandlerContext } from './ContentHandler';

export class ReasoningHandler {
  private logger: ILogger;

  constructor(
    private insertBeforeBody: (ctx: StreamHandlerContext, el: HTMLElement) => void,
    private autoScroll: (msgEl: HTMLElement) => void,
    private debug?: IDebugManager,
  ) {
    this.logger = getLogger('stream');
  }

  handleReasoning(data: string, ctx: StreamHandlerContext): void {
    this.debug?.logStream('reasoning', data);
    this.logger.debug('reasoning', { len: data.length });
    let details = ctx.msgEl.querySelector(`details.${C.REASONING}[data-phase="${ctx.phaseIndex}"]`) as HTMLDetailsElement | null;
    if (!details) {
      details = document.createElement('details');
      details.className = C.REASONING;
      details.dataset.phase = String(ctx.phaseIndex);
      details.open = true;
      details.innerHTML = `<summary>${ctx.phaseIndex === 0 ? 'Razonando...' : 'Razonamiento (Fase ' + (ctx.phaseIndex + 1) + ')'}</summary><div class="${C.RT}"></div>`;
      this.insertBeforeBody(ctx, details);
    }
    const rt = details.querySelector('.' + C.RT) as HTMLElement;
    if (rt) rt.textContent = (rt.textContent || '') + data;
    if (!ctx.reasoningTexts[ctx.phaseIndex]) ctx.reasoningTexts[ctx.phaseIndex] = '';
    ctx.reasoningTexts[ctx.phaseIndex] += data;
    this.autoScroll(ctx.msgEl);
  }

  handleMemory(data: string, ctx: StreamHandlerContext): void {
    this.debug?.logStream('memory', data);
    let details = ctx.msgEl.querySelector('details.' + C.REASONING + '.memories-phase') as HTMLDetailsElement | null;
    if (!details) {
      details = document.createElement('details');
      details.className = C.REASONING_MEMORIES;
      details.open = true;
      details.innerHTML = `<summary>📖 Memorias</summary><div class="${C.MEMORY_CONTENT}"></div>`;
      this.insertBeforeBody(ctx, details);
    }
    const contentEl = details.querySelector('.' + C.RT + '.memory-content') as HTMLElement;
    if (contentEl) contentEl.textContent = (contentEl.textContent || '') + data;
    this.autoScroll(ctx.msgEl);
  }
}
