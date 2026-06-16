import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { SessionList } from '../core/session/SessionList';
import { IEventBus } from '../types/events';
import { TypedEventBus } from '../core/infra/EventBus';

describe('SessionList DOM contract', () => {
  let sessionList: SessionList;
  let eventBus: IEventBus;
  let sidebarEl: HTMLElement;

  beforeEach(() => {
    document.getElementById('session-list')?.remove();
    eventBus = new TypedEventBus();
    sidebarEl = document.createElement('div');
    sidebarEl.id = 'session-list';
    document.body.appendChild(sidebarEl);

    sessionList = new SessionList(eventBus);
    sessionList.init();
  });

  afterEach(() => {
    sidebarEl.remove();
  });

  const sessions = [
    { id: 'sess_001', name: 'Chat about AI', count: 5, last_str: '2026-06-16T10:00:00Z' },
    { id: 'tele_abc', name: 'Telegram chat', count: 3, last_str: '2026-06-16T09:00:00Z' },
    { id: 'sess_003', name: 'Research', count: 12, last_str: '2026-06-15T18:00:00Z' },
  ];

  it('renders session items', () => {
    sessionList.renderSessions(sessions, 'sess_001');
    const items = sidebarEl.querySelectorAll('.session-item');
    expect(items.length).toBe(3);
  });

  it('marks active session with .active class', () => {
    sessionList.renderSessions(sessions, 'sess_001');
    const activeItem = sidebarEl.querySelector('.session-item.active');
    expect(activeItem).not.toBeNull();
    expect(activeItem!.getAttribute('data-sid')).toBe('sess_001');
  });

  it('renders Telegram icon for tele_ prefixed sessions', () => {
    sessionList.renderSessions(sessions, 'sess_001');
    const tgItem = sidebarEl.querySelector('.session-item[data-sid="tele_abc"]');
    const icon = tgItem!.querySelector('.session-icon-tg');
    expect(icon).not.toBeNull();
  });

  it('renders Chat icon for non-telegram sessions', () => {
    sessionList.renderSessions(sessions, 'sess_001');
    const chatItem = sidebarEl.querySelector('.session-item[data-sid="sess_001"]');
    const icon = chatItem!.querySelector('.session-icon-chat');
    expect(icon).not.toBeNull();
  });

  it('has session-label with session name', () => {
    sessionList.renderSessions(sessions, 'sess_001');
    const item = sidebarEl.querySelector('.session-item[data-sid="sess_001"]');
    const label = item!.querySelector('.session-label');
    expect(label!.textContent).toBe('Chat about AI');
  });

  it('has session-meta with message count', () => {
    sessionList.renderSessions(sessions, 'sess_001');
    const item = sidebarEl.querySelector('.session-item[data-sid="sess_001"]');
    const meta = item!.querySelector('.session-meta');
    expect(meta!.textContent).toContain('5 msgs');
  });

  it('has rename and delete buttons', () => {
    sessionList.renderSessions(sessions, 'sess_001');
    const item = sidebarEl.querySelector('.session-item[data-sid="sess_001"]');
    expect(item!.querySelector('.act-rename')).not.toBeNull();
    expect(item!.querySelector('.act-delete')).not.toBeNull();
  });

  it('supports markUnread and clearUnread', () => {
    sessionList.renderSessions(sessions, 'sess_001');

    sessionList.markUnread('sess_003');
    let item = sidebarEl.querySelector('.session-item[data-sid="sess_003"]');
    expect(item!.classList.contains('has-new')).toBe(true);

    sessionList.clearUnread('sess_003');
    item = sidebarEl.querySelector('.session-item[data-sid="sess_003"]');
    expect(item!.classList.contains('has-new')).toBe(false);
  });

  it('markUnread adds has-new to active session (no active check)', () => {
    sessionList.renderSessions(sessions, 'sess_001');
    sessionList.markUnread('sess_001');

    const item = sidebarEl.querySelector('.session-item[data-sid="sess_001"]');
    expect(item!.classList.contains('has-new')).toBe(true);
  });
});
