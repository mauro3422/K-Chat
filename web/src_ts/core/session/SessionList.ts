import { IEventBus } from '../../types/events';
import { getLogger } from '../infra/LoggerFactory';
import { ILogger } from '../infra/Logger';

const CHAT_ICON = `<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.2L4 17.2V4h16v12z"/></svg>`;

const TELEGRAM_ICON = `<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M9.8 16.2l-.4 3.2c.2 0 .4-.1.5-.2l2.2-2.1 4.6 3.4c.8.5 1.4.2 1.6-.7l2.8-13.5"/><path d="M1 11.5l5.8 2.2 2.7 8.9"/><path d="M9.8 16.2l9.5-5.9"/></svg>`;

const RENAME_ICON = `<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>`;

const DELETE_ICON = `<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>`;

const CHECK_ICON = `<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>`;

const CANCEL_ICON = `<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>`;

export interface SessionListEntry {
  id: string;
  name: string;
  count?: number;
  last_str?: string;
  node_id?: string;
  node_role?: string;
  node_platform?: string;
  cluster_name?: string;
  source_url?: string;
  source_mode?: string;
  is_favorite?: boolean;
}

export class SessionList {
  private sidebarEl: HTMLElement | null = null;
  private eventBus: IEventBus;
  private logger: ILogger = getLogger('session-list');
  private unreadSessions = new Set<string>();

  constructor(eventBus: IEventBus) {
    this.eventBus = eventBus;
  }

  markUnread(sessionId: string): void {
    this.unreadSessions.add(sessionId);
    const itemEl = this.sidebarEl?.querySelector(`.session-item[data-sid="${sessionId}"]`) as HTMLElement | null;
    if (itemEl) {
      itemEl.classList.add('has-new');
    }
  }

  clearUnread(sessionId: string): void {
    this.unreadSessions.delete(sessionId);
    const itemEl = this.sidebarEl?.querySelector(`.session-item[data-sid="${sessionId}"]`) as HTMLElement | null;
    if (itemEl) {
      itemEl.classList.remove('has-new');
    }
  }

  get unreadCount(): number {
    return this.unreadSessions.size;
  }

  init(): void {
    this.sidebarEl = document.getElementById('session-list');
    if (!this.sidebarEl) {
      console.warn('session-list not found in DOM.');
    }
  }

  renderSessions(sessions: SessionListEntry[], activeId: string): void {
    if (!this.sidebarEl) return;

    this.logger.info('render_sessions', `total=${sessions.length} activeId=${activeId}`);
    this.sidebarEl.innerHTML = '';
    const fragment = document.createDocumentFragment();

    sessions.forEach((s) => {
      const isTelegram = s.id.startsWith('tele_');
      const label = s.name || s.id.substring(0, 8);
      const msgCount = s.count !== undefined ? s.count : 0;
      const lastStr = s.last_str ? s.last_str.substring(0, 10) : new Date().toISOString().substring(0, 10);
      const meta = `${msgCount} exchanges - ${lastStr}`;
      
      const itemEl = document.createElement('div');
      itemEl.className = `session-item ${s.id === activeId ? 'active' : ''}`;
      if (this.unreadSessions.has(s.id) && s.id !== activeId) {
        itemEl.classList.add('has-new');
      }
      itemEl.dataset.sid = s.id;

      const mainEl = document.createElement('div');
      mainEl.className = 'session-main';

      const previewEl = document.createElement('div');
      previewEl.className = 'session-preview';

      // SVG Icon
      const wrapper = document.createElement('div');
      wrapper.innerHTML = isTelegram ? TELEGRAM_ICON : CHAT_ICON;
      const svgEl = wrapper.firstElementChild! as SVGElement;
      svgEl.setAttribute('class', `session-icon ${isTelegram ? 'session-icon-tg' : 'session-icon-chat'}`);

      const labelEl = document.createElement('span');
      labelEl.className = 'session-label';
      labelEl.textContent = label;

      previewEl.appendChild(svgEl);
      previewEl.appendChild(labelEl);

      if (s.node_id) {
        const originEl = document.createElement('span');
        originEl.className = 'session-origin';
        const platform = (s.node_platform || '').toLowerCase();
        const role = (s.node_role || 'secondary').toLowerCase();
        originEl.title = `${s.node_id} · ${platform || 'sistema desconocido'} · ${role}`;
        originEl.setAttribute('aria-label', originEl.title);

        if (platform === 'linux' || platform === 'windows') {
          const osIcon = document.createElement('img');
          osIcon.className = 'session-origin-icon';
          osIcon.src = `/static/icons/node-${platform}.svg`;
          osIcon.alt = platform === 'linux' ? 'Linux' : 'Windows';
          originEl.appendChild(osIcon);
        }

        const roleIcon = document.createElement('img');
        roleIcon.className = `session-origin-icon session-role-${role}`;
        roleIcon.src = `/static/icons/node-${role === 'primary' ? 'primary' : 'secondary'}.svg`;
        roleIcon.alt = role === 'primary' ? 'Primario' : 'Secundario';
        originEl.appendChild(roleIcon);
        previewEl.appendChild(originEl);
      }

      // Actions (Rename / Delete)
      const actionsEl = document.createElement('div');
      actionsEl.className = 'session-actions';

      const renameBtn = document.createElement('button');
      renameBtn.className = 'act-rename';
      renameBtn.title = 'Renombrar';
      renameBtn.insertAdjacentHTML('beforeend', RENAME_ICON);

      renameBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.logger.info('rename_prompt', `sessionId=${s.id} currentLabel=${label}`);

        const nameSpan = itemEl.querySelector('.session-label') as HTMLElement;
        if (!nameSpan) return;
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'session-rename-input';
        input.value = label;
        input.style.width = '100%';
        input.style.boxSizing = 'border-box';
        nameSpan.textContent = '';
        nameSpan.appendChild(input);
        input.focus();
        input.select();

        // Hide normal actions, show confirm/cancel
        actionsEl.innerHTML = '';

        const confirmBtn = document.createElement('button');
        confirmBtn.className = 'act-confirm';
        confirmBtn.title = 'Confirmar';
        confirmBtn.insertAdjacentHTML('beforeend', CHECK_ICON);

        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'act-cancel';
        cancelBtn.title = 'Cancelar';
        cancelBtn.insertAdjacentHTML('beforeend', CANCEL_ICON);

        const submitRename = () => {
          const newName = input.value.trim();
          if (newName && newName !== label) {
            this.eventBus.emit('session:rename', { sessionId: s.id, name: newName });
            this.logger.info('rename_submit', `sessionId=${s.id} name=${newName}`);
          } else {
            nameSpan.textContent = label;
          }
        };

        const cancelRename = () => {
          nameSpan.textContent = label;
          // Restore normal actions
          restoreActions();
        };

        const restoreActions = () => {
          actionsEl.innerHTML = '';
          actionsEl.appendChild(renameBtn);
          actionsEl.appendChild(deleteBtn);
        };

        confirmBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          submitRename();
        });
        cancelBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          cancelRename();
        });

        input.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') { e.preventDefault(); submitRename(); }
          if (e.key === 'Escape') { e.preventDefault(); cancelRename(); }
        });

        actionsEl.appendChild(confirmBtn);
        actionsEl.appendChild(cancelBtn);
      });

      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'act-delete';
      deleteBtn.title = 'Eliminar';
      deleteBtn.insertAdjacentHTML('beforeend', DELETE_ICON);

      deleteBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.logger.info('delete_prompt', `sessionId=${s.id} label=${label}`);

        // Replace actions with confirm/cancel
        actionsEl.innerHTML = '';

        const confirmBtn = document.createElement('button');
        confirmBtn.className = 'act-confirm';
        confirmBtn.title = 'Confirmar eliminación';
        confirmBtn.insertAdjacentHTML('beforeend', CHECK_ICON);

        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'act-cancel';
        cancelBtn.title = 'Cancelar';
        cancelBtn.insertAdjacentHTML('beforeend', CANCEL_ICON);

        confirmBtn.addEventListener('click', (e2) => {
          e2.stopPropagation();
          this.logger.info('delete_confirm', `sessionId=${s.id} label=${label}`);
          this.eventBus.emit('session:delete', { sessionId: s.id });
        });
        cancelBtn.addEventListener('click', (e2) => {
          e2.stopPropagation();
          // Restore normal actions
          actionsEl.innerHTML = '';
          actionsEl.appendChild(renameBtn);
          actionsEl.appendChild(deleteBtn);
        });

        actionsEl.appendChild(confirmBtn);
        actionsEl.appendChild(cancelBtn);
      });

      actionsEl.appendChild(renameBtn);
      actionsEl.appendChild(deleteBtn);

      mainEl.appendChild(previewEl);
      mainEl.appendChild(actionsEl);

      const metaEl = document.createElement('div');
      metaEl.className = 'session-meta';
      metaEl.textContent = meta;

      itemEl.appendChild(mainEl);
      itemEl.appendChild(metaEl);

      itemEl.addEventListener('click', () => {
        this.logger.info('select_click', `sessionId=${s.id}`);
        this.eventBus.emit('session:select', { sessionId: s.id });
      });

      fragment.appendChild(itemEl);
    });

    this.sidebarEl.appendChild(fragment);
  }
}
