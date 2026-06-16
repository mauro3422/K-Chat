import { C } from '../core/DomContracts';
import { IDebugManager } from '../types/debug';
import { ToolCallPayload } from '../types/streaming';
import type { StreamHandlerContext } from './ContentHandler';

export class ToolCallRenderer {
  constructor(
    private insertBeforeBody: (ctx: StreamHandlerContext, el: HTMLElement) => void,
    private autoScroll: (msgEl: HTMLElement) => void,
    private debug?: IDebugManager,
  ) {}

  handleToolCall(data: string, ctx: StreamHandlerContext): void {
    let payload: ToolCallPayload;
    try { payload = JSON.parse(data) as ToolCallPayload; } catch { payload = { status: 'calling', name: data }; }
    this.debug?.logStream('tool_call', `${payload.status} ${payload.name}`);
    const status = payload.status || 'calling';
    const toolName = payload.name || 'unknown';
    let wrapper = ctx.msgEl.querySelector(`.${C.TOOL_CALLS}[data-phase="${ctx.phaseIndex}"]`) as HTMLElement | null;
    if (!wrapper) {
      wrapper = document.createElement('div');
      wrapper.className = C.TOOL_CALLS;
      wrapper.dataset.phase = String(ctx.phaseIndex);
      this.insertBeforeBody(ctx, wrapper);
    }
    const existing = wrapper.querySelector(`.${C.TC_ITEM}[data-tool="${toolName}"]`) as HTMLElement | null;
    if (existing) {
      existing.className = C.TC_ITEM + ' ' + status;
      existing.innerHTML = status === 'ok' ? `&#10003; ${toolName}` : status === 'error' ? `&#10007; ${toolName}` : `⚡ ${toolName}`;
    } else if (status === 'calling') {
      const pill = document.createElement('span');
      pill.className = C.TC_ITEM_CALLING;
      pill.dataset.tool = toolName;
      pill.innerHTML = `<span class="tc-spinner"></span> ${toolName}`;
      wrapper.appendChild(pill);
    } else {
      const pill = document.createElement('span');
      pill.className = C.TC_ITEM + ' ' + status;
      pill.dataset.tool = toolName;
      pill.innerHTML = status === 'ok' ? `&#10003; ${toolName}` : `&#10007; ${toolName}`;
      wrapper.appendChild(pill);
    }
    if (status !== 'calling') ctx.phaseIndex++;
    this.autoScroll(ctx.msgEl);
  }
}
