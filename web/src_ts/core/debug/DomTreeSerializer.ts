/**
 * DomTreeSerializer — serializes DOM element trees to HTML or plain text.
 * Pure logic, no state, no DOM queries.
 */
export class DomTreeSerializer {
  /**
   * Render DOM tree as HTML (for the debug panel).
   */
  renderTree(el: Node, depth: number): string {
    if (el.nodeType === Node.TEXT_NODE) {
      const txt = (el.textContent || '').trim();
      if (!txt) return '';
      return `<div class="dbg-tree-text" style="padding-left:${depth * 12}px">"${this.esc(txt.substring(0, 60))}"</div>`;
    }
    if (el.nodeType !== Node.ELEMENT_NODE) return '';

    const e = el as HTMLElement;
    const tag = e.tagName.toLowerCase();
    const cls = e.getAttribute('class') || '';

    let html = `<div class="dbg-tree-elem" style="padding-left:${depth * 12}px">`;
    html += `<span class="dbg-tag">&lt;${tag}</span>`;
    if (e.id) html += `<span class="dbg-id">#${e.id}</span>`;
    if (cls) html += `<span class="dbg-cls">.${cls.split(' ').slice(0, 2).join('.')}</span>`;

    if (tag === 'iframe' || tag === 'div') {
      const rect = e.getBoundingClientRect();
      if (rect.width > 0 || rect.height > 0) {
        html += ` <span class="dbg-dim">${Math.round(rect.width)}×${Math.round(rect.height)}px</span>`;
      }
    }

    html += `&gt;</div>`;

    for (let i = 0; i < e.children.length; i++) {
      html += this.renderTree(e.children[i], depth + 1);
    }
    return html;
  }

  /**
   * Render DOM tree as plain text (for Copy All).
   */
  renderTreeText(el: Node, depth: number): string {
    if (el.nodeType === Node.TEXT_NODE) {
      const txt = (el.textContent || '').trim();
      if (!txt) return '';
      return '  '.repeat(depth) + `"${txt.substring(0, 60)}"`;
    }
    if (el.nodeType !== Node.ELEMENT_NODE) return '';

    const e = el as HTMLElement;
    const tag = e.tagName.toLowerCase();
    const cls = e.getAttribute('class') || '';
    let line = '  '.repeat(depth) + `<${tag}`;
    if (e.id) line += ` #${e.id}`;
    if (cls) line += ` .${cls.split(' ').slice(0, 2).join('.')}`;
    if (cls.includes('interactive-widget-container') || tag === 'iframe') {
      const rect = e.getBoundingClientRect();
      line += ` [${Math.round(rect.width)}x${Math.round(rect.height)}]`;
    }
    line += '>';

    let result = line + '\n';
    for (let i = 0; i < e.children.length; i++) {
      result += this.renderTreeText(e.children[i], depth + 1);
    }
    return result;
  }

  private esc(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
}
