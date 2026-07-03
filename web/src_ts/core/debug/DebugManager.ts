import { DomTreeSerializer } from './DomTreeSerializer';
import { IDebugManager } from '../../types/debug';
import { ApiClient } from '../../api/ApiClient';

type LogEntry = {
  id: number;
  at: string;
  t: string;
  d: string;
};

type BackendLogEntry = {
  ts: number;
  level: string;
  message: string;
};

export class DebugManager implements IDebugManager {
  private contentEl: HTMLElement | null = null;

  private streamLog: LogEntry[] = [];
  private uiLog: LogEntry[] = [];
  private widgetLog: LogEntry[] = [];

  private backendLogs: BackendLogEntry[] = [];
  private debugInfo: Record<string, unknown> | null = null;
  private sessionId: string = '';

  private nextId = 1;
  private maxEntries = 100;
  private panelEl: HTMLElement | null = null;

  private activeMsgEl: HTMLElement | null = null;
  private activeState: Record<string, unknown> | null = null;

  private treeSerializer = new DomTreeSerializer();
  private apiClient = new ApiClient();

  private refreshQueued = false;

  init(): void {
    this.contentEl = document.getElementById('debug-content');
    this.panelEl = document.getElementById('debug-panel');
    if (this.contentEl) {
      this.contentEl.addEventListener('click', (e) => this.handleCopyClick(e));
    }
  }

  setSessionId(sessionId: string): void {
    this.sessionId = sessionId;
  }

  async loadDebugInfo(sessionId: string): Promise<void> {
    try {
      const resp = await this.apiClient.loadDebugInfo(sessionId);
      const data = await resp.json();
      this.debugInfo = data as Record<string, unknown>;
    } catch {
      this.debugInfo = { error: 'Failed to load debug info' };
    }
    this.refresh();
  }

  async loadBackendLogs(): Promise<void> {
    try {
      const resp = await this.apiClient.loadBackendLogs();
      const data = await resp.json();
      this.backendLogs = (data.logs || []) as BackendLogEntry[];
    } catch {
      this.backendLogs = [];
    }
    this.refresh();
  }

  logStream(type: string, detail: string): void {
    const entry = this.makeEntry(type, detail);
    this.streamLog.push(entry);
    if (this.streamLog.length > this.maxEntries) this.streamLog.shift();
    this.scheduleRefresh();
  }

  logUI(label: string, detail: string): void {
    const entry = this.makeEntry(label, detail);
    this.uiLog.push(entry);
    if (this.uiLog.length > this.maxEntries) this.uiLog.shift();
    this.scheduleRefresh();
  }

  logWidget(detail: string): void {
    const entry = this.makeEntry('widget', detail);
    this.widgetLog.push(entry);
    if (this.widgetLog.length > 50) this.widgetLog.shift();
    this.scheduleRefresh();
  }

  setActiveMessage(el: HTMLElement | null, state: Record<string, unknown> | null): void {
    this.activeMsgEl = el;
    this.activeState = state;
  }

  refresh(): void {
    if (!this.contentEl) return;

    // Save scroll positions of pre elements and details
    const scrollPositions: Record<string, number> = {};
    if (this.contentEl) {
      this.contentEl.querySelectorAll('pre.db-pre, .dbg-dom, .sl-container').forEach((el, i) => {
        const key = (el.id || `scroll-${i}`);
        scrollPositions[key] = el.scrollTop;
      });
    }

    let html = '';
    const durations = this.calcStreamDurations();

    html += '<div style="text-align:right;margin-bottom:8px">';
    html += '<button class="db-copy" data-copy-action="all" style="float:none;font-size:11px">📋 Copy All Debug</button>';
    html += '</div>';

    if (this.debugInfo) {
      html += this.renderDebugInfoSection();
    }

    if (durations.length > 0) {
      html += '<div class="db-section"><strong>⏱️ Stream Durations</strong></div>';
      for (const d of durations) {
        html += this.row(d.label, d.duration);
      }
    }

    html += '<div class="db-section"><strong>⚙️ Stream State</strong></div>';
    if (this.activeState) {
      html += this.row('Phase', this.activeState.phaseIndex);
      html += this.row('First Token', this.activeState.firstToken);
      html += this.row('Reasoning Phases', ((this.activeState.reasoningTexts as string[] | undefined) || []).filter(Boolean).length);
      html += this.row('Content Phases', ((this.activeState.contentTexts as string[] | undefined) || []).filter(Boolean).length);
    } else {
      html += '<div class="dbg-muted">⏸️ idle</div>';
    }

    html += this.renderLogSection('📥 Stream Log', this.streamLog, 30, 'stream');
    html += this.renderLogSection('🖱️ UI Log', this.uiLog, 30, 'ui');
    html += this.renderLogSection('🧩 Widget Log', this.widgetLog, 20, 'widgets');
    html += this.renderWidgetDomSection();
    html += this.renderBackendLogsSection();

    // Full session messages JSON (auto-loaded from debugInfo)
    const hasSessionData = this.debugInfo && Object.keys(this.debugInfo).length > 0;
    if (hasSessionData) {
      html += `<details class="db-section" open>
        <summary><strong>📦 Session Data</strong> <button class="db-copy" data-copy-action="all-session" style="font-size:10px;padding:1px 6px">📋 Copy</button></summary>
        <pre class="db-pre" style="max-height:500px">${this.esc(JSON.stringify(this.debugInfo, null, 2))}</pre>
      </details>`;
    }

    html += `<details class="db-section" open>
      <summary><strong>📄 DOM Tree</strong></summary>
      <div class="dbg-dom" id="dom-tree">`;
    if (this.activeMsgEl) {
      try {
        html += this.treeSerializer.renderTree(this.activeMsgEl, 0);
      } catch (e) {
        html += `<div class="dbg-muted">(error: ${(e as Error).message || String(e)})</div>`;
      }
    } else {
      html += '<div class="dbg-muted">(no active message)</div>';
    }
    html += `</div></details>`;

    this.contentEl.innerHTML = html;

    // Restore scroll positions after layout completes
    if (Object.keys(scrollPositions).length > 0) {
      requestAnimationFrame(() => {
        this.contentEl!.querySelectorAll('pre.db-pre, .dbg-dom, .sl-container').forEach((el, i) => {
          const key = (el.id || `scroll-${i}`);
          const saved = scrollPositions[key];
          if (saved !== undefined) {
            el.scrollTop = saved;
          }
        });
      });
    }
  }

  getAllText(): string {
    const parts: string[] = [];

    if (this.debugInfo) {
      parts.push('=== DEBUG INFO ===');
      const d = this.debugInfo;
      if (d.model) parts.push(`Model: ${d.model}`);
      if (d.reasoning) parts.push(`Reasoning:\n${d.reasoning}`);
      if (d.auto_memories) parts.push(`Auto Memories:\n${d.auto_memories}`);
      if (d.phases) {
        try {
          parts.push(`Phases:\n${JSON.stringify(JSON.parse(d.phases as string), null, 2)}`);
        } catch {
          parts.push(`Phases: ${d.phases}`);
        }
      }
      if (d.tool_calls) parts.push(`Tool Calls:\n${JSON.stringify(d.tool_calls, null, 2)}`);
      if (d.system_prompt) parts.push(`System Prompt:\n${(d.system_prompt as string).substring(0, 2000)}`);
      if (d.history_before) parts.push(`History:\n${JSON.stringify(d.history_before, null, 2)}`);
      parts.push('');
    }

    const durations = this.calcStreamDurations();
    if (durations.length > 0) {
      parts.push('=== STREAM DURATIONS ===');
      for (const d of durations) {
        parts.push(`${d.label}: ${d.duration}`);
      }
      parts.push('');
    }

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
        parts.push(`${e.id} ${e.at} ${e.t} ${e.d}`);
      }
    }

    parts.push('');
    parts.push('=== UI EVENTS ===');
    if (this.uiLog.length === 0) {
      parts.push('(none)');
    } else {
      for (const e of this.uiLog) {
        parts.push(`${e.id} ${e.at} ${e.t} ${e.d}`);
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
    parts.push('=== WIDGET DOM ===');
    const widgetContainers = document.querySelectorAll('[data-widget-id]');
    if (widgetContainers.length === 0) {
      parts.push('(none)');
    } else {
      for (const container of widgetContainers) {
        const wid = container.getAttribute('data-widget-id') || '?';
        const iframe = container.querySelector('iframe');
        parts.push(`--- ${wid} ---`);
        parts.push(`iframe=${iframe ? iframe.offsetHeight + 'px' : '-'}`);
      }
    }

    parts.push('');
    parts.push('=== BACKEND LOGS ===');
    if (this.backendLogs.length === 0) {
      parts.push('(none)');
    } else {
      for (const log of this.backendLogs) {
        const ts = new Date(log.ts * 1000).toISOString().slice(11, 23);
        parts.push(`${ts} ${log.level} ${log.message}`);
      }
    }

    parts.push('');
    parts.push('=== DOM TREE ===');
    if (this.activeMsgEl) {
      try {
        parts.push(this.treeSerializer.renderTreeText(this.activeMsgEl, 0));
      } catch (e) {
        parts.push(`(error rendering DOM tree: ${(e as Error).message || String(e)})`);
      }
    } else {
      parts.push('(none)');
    }

    return parts.join('\n');
  }

  // ── Private: Render ─────────────────────────────────

  private renderLogSection(title: string, entries: LogEntry[], limit: number, copyAction?: string): string {
    let html = `<details class="db-section" open>
      <summary><strong>${title} (${entries.length})</strong>`;
    if (copyAction) {
      html += ` <button class="db-copy" data-copy-action="${copyAction}" style="float:right;font-size:11px">📋 Copy</button>`;
    }
    html += `</summary>
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

  private renderDebugInfoSection(): string {
    let html = '';
    const d = this.debugInfo!;

    if (d.model) html += this.row('Model', d.model);
    html += this.renderPreSection('🧠 Reasoning', (d.reasoning as string) || '(none)');
    html += this.renderPreSection('💾 Auto Memories', (d.auto_memories as string) || '(none)');

    const rawPhases = (d.phases as string) || '[]';
    let phasesStr: string;
    try {
      phasesStr = JSON.stringify(JSON.parse(rawPhases), null, 2);
    } catch {
      phasesStr = rawPhases;
    }
    html += this.renderDetailsPreSection('⚙️ Phases', phasesStr, true);
    html += this.renderPreSection('🔧 Tool Calls', JSON.stringify(d.tool_calls || [], null, 2));
    html += this.renderPreSection('📝 System Prompt', ((d.system_prompt as string) || '').substring(0, 2000));

    const history = (d.history_before as unknown[]) || [];
    html += this.renderDetailsPreSection(`📜 History (${history.length})`, JSON.stringify(history, null, 2), false);

    return html;
  }

  private renderPreSection(title: string, text: string): string {
    return `<div class="db-section"><strong>${title}</strong>` +
      `<button class="db-copy" data-copy-action="text" style="float:right;font-size:11px">📋 Copy</button>` +
      `<pre class="db-pre">${this.esc(text)}</pre></div>`;
  }

  private renderDetailsPreSection(title: string, text: string, open: boolean): string {
    return `<details class="db-section"${open ? ' open' : ''}>
      <summary><strong>${title}</strong>` +
      `<button class="db-copy" data-copy-action="text" style="float:right;font-size:11px">📋 Copy</button>` +
      `</summary><pre class="db-pre">${this.esc(text)}</pre></details>`;
  }

  private renderWidgetDomSection(): string {
    const containers = document.querySelectorAll('[data-widget-id]');
    let html = `<details class="db-section" open>
      <summary><strong>🖼️ Widget DOM (${containers.length})</strong>
      <button class="db-copy" data-copy-action="text" style="float:right;font-size:11px">📋 Copy</button>
      </summary>`;
    if (containers.length === 0) {
      html += '<div class="dbg-muted">(no widget containers found)</div>';
    } else {
      html += '<pre class="db-pre">';
      for (const c of containers) {
        const wid = c.getAttribute('data-widget-id') || '?';
        const iframe = c.querySelector('iframe');
        html += `--- ${this.esc(wid)} ---\n`;
        html += `iframe=${iframe ? iframe.offsetHeight + 'px' : '-'}\n`;
        const events = this.widgetLog.filter(e => e.d.includes(wid));
        for (const e of events.slice(-10)) {
          html += `${e.at} ${this.esc(e.t)} ${this.esc(e.d.substring(0, 120))}\n`;
        }
      }
      html += '</pre>';
    }
    html += '</details>';
    return html;
  }

  private renderBackendLogsSection(): string {
    let html = `<details class="db-section" open>
      <summary><strong>🖥️ Backend Logs (${this.backendLogs.length})</strong>
      <button class="db-copy" data-copy-action="backend" style="float:right;font-size:11px">📋 Copy</button>
      </summary>
      <div class="sl-container">`;
    if (this.backendLogs.length === 0) {
      html += '<div class="sl-item" style="color:var(--text-muted);font-style:italic">(no logs loaded)</div>';
    } else {
      for (const log of this.backendLogs.slice(-50)) {
        const ts = new Date(log.ts * 1000).toISOString().slice(11, 23);
        let levelClass = 'sl-info';
        if (log.level === 'ERROR') levelClass = 'sl-error';
        else if (log.level === 'WARNING') levelClass = 'sl-warning';
        html += `<div class="sl-item ${levelClass}">`;
        html += `<span class="sl-ts">${ts}</span>`;
        html += `<span class="sl-tag">${this.esc(log.level)}</span>`;
        html += `<span class="sl-data">${this.esc(log.message.substring(0, 300))}</span>`;
        html += `</div>`;
      }
    }
    html += `</div></details>`;
    return html;
  }

  // ── Private: Duration ────────────────────────────────

  private calcStreamDurations(): Array<{ label: string; duration: string }> {
    const starts: Record<number, { at: string; label: string }> = {};
    const results: Array<{ label: string; duration: string }> = [];

    for (const e of this.uiLog) {
      if (e.t === 'stream_start') {
        starts[e.id] = { at: e.at, label: e.d.substring(0, 60) };
      }
    }

    for (const e of this.uiLog) {
      if (e.t === 'stream_complete') {
        for (const sid of Object.keys(starts)) {
          const s = starts[Number(sid)];
          const startMs = this.timeToMs(s.at);
          const endMs = this.timeToMs(e.at);
          if (startMs !== null && endMs !== null && endMs > startMs) {
            const dur = ((endMs - startMs) / 1000).toFixed(1);
            results.push({ label: `${s.at} → ${e.at}`, duration: `${dur}s "${s.label}"` });
            delete starts[Number(sid)];
            break;
          }
        }
      }
    }

    return results;
  }

  private timeToMs(t: string): number | null {
    if (!t) return null;
    const p = t.split(':');
    if (p.length !== 3) return null;
    return (parseInt(p[0], 10) * 3600 + parseInt(p[1], 10) * 60 + parseFloat(p[2])) * 1000;
  }

  // ── Private: Copy ────────────────────────────────────

  private handleCopyClick(e: Event): void {
    const target = e.target as Node;
    // e.target can be a text node (e.g. clicking on emoji inside button)
    // — closest() only exists on Element, not on Text nodes.
    const el = target.nodeType === Node.TEXT_NODE ? target.parentElement : target as Element;
    const btn = el?.closest('.db-copy') as HTMLElement | null;
    if (!btn) return;
    const action = btn.getAttribute('data-copy-action');
    console.log('[debug] copy click', { action, btnText: btn.textContent });
    if (action === 'all') this.copyAll(btn);
    else if (action === 'stream') this.copyStreamSection(btn);
    else if (action === 'ui') this.copyUISection(btn);
    else if (action === 'widgets') this.copyWidgetSection(btn);
    else if (action === 'backend') this.copyBackendSection(btn);
    else if (action === 'text') this.copyPreText(btn);
  }

  private copyAll(btnEl: HTMLElement): void {
    const text = this.getAllText();
    this.copyText(text, btnEl);
  }

  private copyStreamSection(btn: HTMLElement): void {
    const text = this.streamLog.map(e => `${e.id} ${e.at} ${e.t} ${e.d}`).join('\n');
    this.copyText(text, btn);
  }

  private copyUISection(btn: HTMLElement): void {
    const text = this.uiLog.map(e => `${e.id} ${e.at} ${e.t} ${e.d}`).join('\n');
    this.copyText(text, btn);
  }

  private copyWidgetSection(btn: HTMLElement): void {
    const text = this.widgetLog.map(e => `${e.at} ${e.t} ${e.d}`).join('\n');
    this.copyText(text, btn);
  }

  private copyBackendSection(btn: HTMLElement): void {
    const text = this.backendLogs.map(log => {
      const ts = new Date(log.ts * 1000).toISOString().slice(11, 23);
      return `${ts} ${log.level} ${log.message}`;
    }).join('\n');
    this.copyText(text, btn);
  }

  private copyPreText(btn: HTMLElement): void {
    const section = btn.closest('.db-section');
    const pre = section?.querySelector('pre');
    if (!pre) { btn.textContent = '[]'; return; }
    this.copyText(pre.textContent || '', btn);
  }

  private copyText(text: string, btn: HTMLElement): void {
    const fallbackCopy = () => {
      try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        return true;
      } catch {
        return false;
      }
    };

    const showResult = (ok: boolean) => {
      const orig = btn.textContent;
      btn.textContent = ok ? '✅ Copied!' : '❌ Error';
      setTimeout(() => { btn.textContent = orig; }, 1500);
    };

    navigator.clipboard.writeText(text).then(
      () => showResult(true),
      () => showResult(fallbackCopy())
    );
  }

  // ── Private: Util ────────────────────────────────────

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
