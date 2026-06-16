/**
 * DebugManager — full debug panel with event logs, DOM tree, and state.
 *
 * Matches the production debug-panel.js structure:
 *  - Stream Log: all NDJSON events with timestamps
 *  - UI Log: user actions, session changes, system events
 *  - Widget Log: widget lifecycle events
 *  - DOM Tree: live DOM snapshot of active message
 *  - Stream State: phase index, firstToken, reasoning/content texts
 *  - Copy All: exports everything as text
 *
 * Delegates DOM tree serialization to DomTreeSerializer.
 */
import { DomTreeSerializer } from './DomTreeSerializer';
import { IDebugManager } from '../../types/debug';

type LogEntry = {
  id: number;
  at: string;       // HH:MM:SS.mmm timestamp
  t: string;         // event type
  d: string;         // detail/data
};

export class DebugManager implements IDebugManager {
  private contentEl: HTMLElement | null = null;

  private streamLog: LogEntry[] = [];
  private uiLog: LogEntry[] = [];
  private widgetLog: LogEntry[] = [];

  private nextId = 1;
  private maxEntries = 100;
  private panelEl: HTMLElement | null = null;

  /** Track the active message DOM element for tree view */
  private activeMsgEl: HTMLElement | null = null;
  private activeState: Record<string, unknown> | null = null;

  private treeSerializer = new DomTreeSerializer();

  init(): void {
    this.contentEl = document.getElementById('debug-content');
    this.panelEl = document.getElementById('debug-panel');
  }

  // ── Log Methods ─────────────────────────────────────

  /** Log a stream event (reasoning, content, tool_call, memory, error) */
  logStream(type: string, detail: string): void {
    const entry = this.makeEntry(type, detail);
    this.streamLog.push(entry);
    if (this.streamLog.length > this.maxEntries) this.streamLog.shift();
    this.scheduleRefresh();
  }

  /** Log a UI event (send message, session change, etc.) */
  logUI(label: string, detail: string): void {
    const entry = this.makeEntry(label, detail);
    this.uiLog.push(entry);
    if (this.uiLog.length > this.maxEntries) this.uiLog.shift();
    this.scheduleRefresh();
  }

  /** Log a widget lifecycle event */
  logWidget(detail: string): void {
    const entry = this.makeEntry('widget', detail);
    this.widgetLog.push(entry);
    if (this.widgetLog.length > 50) this.widgetLog.shift();
    this.scheduleRefresh();
  }

  /** Set the active message DOM element for tree view */
  setActiveMessage(el: HTMLElement | null, state: Record<string, unknown> | null): void {
    this.activeMsgEl = el;
    this.activeState = state;
  }

  // ── Full Render ─────────────────────────────────────

  /** Full refresh — rebuilds the entire debug panel content */
  refresh(): void {
    if (!this.contentEl) return;

    let html = '';

    // ── Copy All button ──
    html += '<div style="text-align:right;margin-bottom:8px">';
    html += '<button class="db-copy" data-copy-action="all" style="float:none;font-size:11px">📋 Copy All Debug</button>';
    html += '</div>';

    // ── Stream State ──
    html += '<div class="db-section"><strong>⚙️ Stream State</strong></div>';
    if (this.activeState) {
      html += this.row('Phase', this.activeState.phaseIndex);
      html += this.row('First Token', this.activeState.firstToken);
      html += this.row('Reasoning Phases', ((this.activeState.reasoningTexts as string[] | undefined) || []).filter(Boolean).length);
      html += this.row('Content Phases', ((this.activeState.contentTexts as string[] | undefined) || []).filter(Boolean).length);
    } else {
      html += '<div class="dbg-muted">⏸️ idle</div>';
    }

    // ── Stream Log ──
    html += this.renderLogSection('📥 Stream Log', this.streamLog, 30);

    // ── UI Log ──
    html += this.renderLogSection('🖱️ UI Log', this.uiLog, 30);

    // ── Widget Log ──
    html += this.renderLogSection('🧩 Widget Log', this.widgetLog, 20);

    // ── DOM Tree ──
    html += `<details class="db-section" open>
      <summary><strong>📄 DOM Tree</strong></summary>
      <div class="dbg-dom" id="dom-tree">`;
    if (this.activeMsgEl) {
      html += this.treeSerializer.renderTree(this.activeMsgEl, 0);
    } else {
      html += '<div class="dbg-muted">(no active message)</div>';
    }
    html += `</div></details>`;

    this.contentEl.innerHTML = html;

    // Bind copy all button
    const copyBtn = this.contentEl.querySelector('[data-copy-action="all"]');
    if (copyBtn) {
      copyBtn.addEventListener('click', () => this.copyAll(copyBtn as HTMLElement));
    }
  }

  /** Get all debug data as text for copy */
  getAllText(): string {
    const parts: string[] = [];

    parts.push('=== STREAM STATE ===');
    if (this.activeState) {
      parts.push(`Phase: ${this.activeState.phaseIndex}`);
      parts.push(`First Token: ${this.activeState.firstToken}`);
      parts.push(`Reasoning Phases: ${((this.activeState.reasoningTexts as string[] | undefined) || []).filter(Boolean).length}`);
      parts.push(`Content Phases: ${((this.activeState.contentTexts as string[] | undefined) || []).filter(Boolean).length}`);
    } else {
      parts.push('(idle)');
    }

    parts.push('');
    parts.push('=== STREAM EVENTS ===');
    if (this.streamLog.length === 0) {
      parts.push('(none)');
    } else {
      for (const e of this.streamLog) {
        parts.push(`${e.at} ${e.t} ${e.d}`);
      }
    }

    parts.push('');
    parts.push('=== UI EVENTS ===');
    if (this.uiLog.length === 0) {
      parts.push('(none)');
    } else {
      for (const e of this.uiLog) {
        parts.push(`${e.at} ${e.t} ${e.d}`);
      }
    }

    parts.push('');
    parts.push('=== WIDGET EVENTS ===');
    if (this.widgetLog.length === 0) {
      parts.push('(none)');
    } else {
      for (const e of this.widgetLog) {
        parts.push(`${e.at} ${e.t} ${e.d}`);
      }
    }

    parts.push('');
    parts.push('=== DOM TREE ===');
    if (this.activeMsgEl) {
      parts.push(this.treeSerializer.renderTreeText(this.activeMsgEl, 0));
    } else {
      parts.push('(none)');
    }

    return parts.join('\n');
  }

  // ── Private ─────────────────────────────────────────

  /** Render a log section as an HTML details/summary */
  private renderLogSection(title: string, entries: LogEntry[], limit: number): string {
    let html = `<details class="db-section" open>
      <summary><strong>${title} (${entries.length})</strong></summary>
      <div class="sl-container">`;
    if (entries.length === 0) {
      html += '<div class="sl-item" style="color:var(--text-muted);font-style:italic">(no events yet)</div>';
    } else {
      for (const e of entries.slice(-limit)) {
        html += `<div class="sl-item">`;
        html += `<span class="sl-ts">${e.at}</span>`;
        html += `<span class="sl-tag">${e.t}</span>`;
        html += `<span class="sl-data">${this.esc(e.d.substring(0, 200))}</span>`;
        html += `</div>`;
      }
    }
    html += `</div></details>`;
    return html;
  }

  /** Copy all debug data to clipboard */
  private copyAll(btnEl: HTMLElement): void {
    const text = this.getAllText();
    navigator.clipboard.writeText(text).then(() => {
      const orig = btnEl.textContent;
      btnEl.textContent = '✅ Copied!';
      setTimeout(() => { btnEl.textContent = orig; }, 1500);
    }).catch(() => {
      btnEl.textContent = '❌ Error';
    });
  }

  private refreshQueued = false;

  private scheduleRefresh(): void {
    if (this.refreshQueued) return;
    this.refreshQueued = true;

    if (this.panelEl && this.panelEl.classList.contains('open')) {
      requestAnimationFrame(() => {
        this.refreshQueued = false;
        this.refresh();
      });
    } else {
      this.refreshQueued = false;
    }
  }

  private makeEntry(type: string, detail: string): LogEntry {
    const now = new Date();
    const at = now.toLocaleTimeString('en-US', { hour12: false }) +
      '.' + String(now.getMilliseconds()).padStart(3, '0');
    return {
      id: this.nextId++,
      at,
      t: type,
      d: detail,
    };
  }

  private row(label: string, val: unknown): string {
    return `<div class="dbg-row"><span class="dbg-label">${label}:</span><span class="dbg-val">${String(val)}</span></div>`;
  }

  private esc(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
}
