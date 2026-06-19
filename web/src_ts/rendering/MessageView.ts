import { IDomRenderer } from '../types/rendering';
import { IIframeBuilder } from '../types/iframe';
import { IMessageView } from '../types/message-view';
import { IWidgetContainerRenderer } from '../types/widget-renderer';
import { C } from '../core/DomContracts';
import { getLogger } from '../core/LoggerFactory';
import { ILogger } from '../core/Logger';
import type { MessageData } from '../types/messages';

/**
 * MessageView — renders message bubbles and manages the messages container.
 *
 * For streaming, it only provides the container (beginStreaming).
 * The ContentHandler fills the details (reasoning, tools, content, widgets).
 * For historical messages, markdown is rendered via DomRenderer which
 * calls registry.extract() before the injected markdown parser.
 */
export class MessageView implements IMessageView {
  private logger: ILogger = getLogger('message-view');
  private containerEl: HTMLElement | null = null;
  private renderer: IDomRenderer;
  private iframeBuilder?: IIframeBuilder;

  constructor(
    renderer: IDomRenderer,
    iframeBuilder?: IIframeBuilder,
    private widgetContainerRenderer?: IWidgetContainerRenderer,
  ) {
    this.renderer = renderer;
    this.iframeBuilder = iframeBuilder;
  }

  init(): void {
    this.containerEl = document.getElementById('messages');
    if (!this.containerEl) {
      console.warn('[MessageView] #messages container not found');
      return;
    }
  }

  /** Append a fully-formed message (from history) */
  appendMessage(msg: MessageData): HTMLElement | null {
    if (!this.containerEl) return null;
    this.logger.info('append', `role=${msg.role} hasReasoning=${!!msg.reasoning} tools=${(msg.matched_tools||[]).length} phases=${(msg.phases||[]).length}`);

    // Remove empty state if present
    const emptyState = this.containerEl.querySelector('.' + C.EMPTY_STATE);
    if (emptyState) emptyState.remove();

    const msgEl = document.createElement('div');
    msgEl.className = `msg ${msg.role}`;
    if (msg.ts) msgEl.dataset.ts = String(msg.ts);
    if (msg.id) msgEl.dataset.id = String(msg.id);

    this._renderMessageContent(msgEl, msg);

    this.containerEl.appendChild(msgEl);

    // Always scroll to show the user's own message
    if (msg.role === 'user') {
      this.containerEl.scrollTop = this.containerEl.scrollHeight;
    }

    return msgEl;
  }

  /** Create an empty streaming bubble — ContentHandler will fill it */
  beginStreaming(role: 'user' | 'assistant'): HTMLElement | null {
    if (!this.containerEl) return null;
    this.logger.info('begin_streaming', `role=${role}`);

    const emptyState = this.containerEl.querySelector('.' + C.EMPTY_STATE);
    if (emptyState) emptyState.remove();

    const msgEl = document.createElement('div');
    msgEl.className = `msg ${role} ${C.LIVE_MSG}`;

    const label = document.createElement('div');
    label.className = C.MSG_LABEL;
    label.textContent = role === 'user' ? 'Tu' : 'Kairos';
    msgEl.appendChild(label);

    // Initial thinking placeholder for assistant
    if (role === 'assistant') {
      const body = document.createElement('div');
      body.className = C.MSG_BODY;
      body.textContent = '✍️ Pensando...';
      msgEl.appendChild(body);
    }

    this.containerEl.appendChild(msgEl);
    // Scroll to show response starts (unconditional — user sent message, expects to see it)
    this.containerEl.scrollTop = this.containerEl.scrollHeight;
    msgEl.dataset.msgId = 'live';

    return msgEl;
  }

  /** Called when streaming ends — live message is finalized */
  endStreaming(): void {
    // Windowing disabled
  }

  /** Clear all messages */
  clearContainer(): void {
    if (this.containerEl) {
      if (this.widgetContainerRenderer) {
        this.widgetContainerRenderer.destroyAll(this.containerEl);
      }
      this.containerEl.innerHTML = '';
      this.logger.info('clear_container');
    }
  }

  // ── Private Helpers ──────────────────────────────────

  /** Render label, delete button, content, and timestamp into an element */
  private _renderMessageContent(el: HTMLElement, msg: MessageData): void {
    // Label
    const label = document.createElement('div');
    label.className = C.MSG_LABEL;
    label.textContent = msg.role === 'user' ? 'Tu' : 'Kairos';
    el.appendChild(label);

    // Delete button
    if (msg.id) {
      const delBtn = document.createElement('button');
      delBtn.className = C.MSG_DELETE_BTN;
      delBtn.title = 'Eliminar mensaje';
      delBtn.textContent = '🗑️';
      delBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (confirm('¿Eliminar este mensaje?')) el.remove();
      });
      el.appendChild(delBtn);
    }

    const content = msg.content || '';
    const reasoning = msg.reasoning || '';
    const matchedTools = msg.matched_tools || [];
    const phases = msg.phases || [];

    if (msg.role === 'assistant' && phases.length > 0) {
      // Multi-phase rendering
      const toolsByTurn: Record<number, Array<{ name: string; status: string }>> = {};
      matchedTools.forEach((t) => {
        const turn = t.turn || 0;
        (toolsByTurn[turn] = toolsByTurn[turn] || []).push({
          name: t.tool_name,
          status: t.status,
        });
      });

      const hasAnyContent = phases.some((p) => p.content);

      phases.forEach((phase, idx) => {
        // Memory block (collapsed in history — expanded during live streaming)
        if (phase.memory) {
          const details = document.createElement('details');
          details.className = C.REASONING_MEMORIES;
          details.innerHTML = `<summary>📖 Memorias</summary><div class="${C.MEMORY_CONTENT}">${this.escapeHtml(phase.memory)}</div>`;
          el.appendChild(details);
        }

        // Reasoning block (collapsed in history — expanded during live streaming)
        if (phase.reasoning) {
          const details = document.createElement('details');
          details.className = C.REASONING;
          details.innerHTML = `<summary>Razonamiento (Fase ${idx + 1})</summary><div class="${C.RT}">${this.escapeHtml(phase.reasoning)}</div>`;
          el.appendChild(details);
        }

        // Content with markdown + widgets
        if (hasAnyContent && phase.content) {
          const body = document.createElement('div');
          body.className = C.MSG_BODY + ' ' + C.MD_CONTENT;
          this.renderWithWidgets(body, phase.content);
          el.appendChild(body);
        }

        // Tool pills
        const turnTools = toolsByTurn[idx + 1] || [];
        if (turnTools.length > 0) {
          const wrapper = document.createElement('div');
          wrapper.className = C.TOOL_CALLS;
          turnTools.forEach((t) => {
            const pill = document.createElement('span');
            pill.className = C.TC_ITEM + ' ' + t.status;
            pill.innerHTML = `${t.status === 'ok' ? '&#10003;' : '&#10007;'} ${this.escapeHtml(t.name)}`;
            wrapper.appendChild(pill);
          });
          el.appendChild(wrapper);
        }
      });

      // Fallback: if no phase content but main content exists
      if (!hasAnyContent && content) {
        const body = document.createElement('div');
        body.className = C.MSG_BODY + ' ' + C.MD_CONTENT;
        this.renderWithWidgets(body, content);
        el.appendChild(body);
      }
    } else {
      // Simple message (no phases)
      if (reasoning) {
        const details = document.createElement('details');
        details.className = C.REASONING;
        details.innerHTML = `<summary>Razonamiento</summary><div class="${C.RT}">${this.escapeHtml(reasoning)}</div>`;
        el.appendChild(details);
      }

      const body = document.createElement('div');
      body.className = msg.role === 'assistant' ? C.MSG_BODY + ' ' + C.MD_CONTENT : C.MSG_BODY;
      this.renderWithWidgets(body, content);
      el.appendChild(body);

      // Tool pills
      if (msg.role === 'assistant' && matchedTools.length > 0) {
        const wrapper = document.createElement('div');
        wrapper.className = C.TOOL_CALLS;
        matchedTools.forEach((t) => {
          const pill = document.createElement('span');
          pill.className = C.TC_ITEM + ' ' + t.status;
          pill.innerHTML = `${t.status === 'ok' ? '&#10003;' : '&#10007;'} ${this.escapeHtml(t.tool_name)}`;
          wrapper.appendChild(pill);
        });
        el.appendChild(wrapper);
      }
    }

    // Timestamp
    if (msg.ts) {
      const ts = document.createElement('div');
      ts.className = C.MSG_TS;
      ts.textContent = typeof msg.ts === 'string' ? msg.ts.substring(0, 16).replace('T', ' ') : String(msg.ts);
      el.appendChild(ts);
    }
  }

  // Windowing disabled (caused duplicate renders + scroll jank)

  private renderWithWidgets(container: HTMLElement, content: string): void {
    // Guard: skip if this container already has this content rendered
    if (container.dataset.contentHash === content) return;
    container.dataset.contentHash = content;

    this.logger.debug('render_with_widgets', `content_length=${content.length}`);
    this.renderer.renderMessage(container, content, true);

    if (this.iframeBuilder) {
      this.iframeBuilder.initAll(container, true);
    }
  }

  private escapeHtml(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
}
