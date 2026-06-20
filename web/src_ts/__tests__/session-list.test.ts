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
    { id: 'sess_001', name: 'Chat about AI', count: 5, last_str: '2026-06-16T10:00:00Z', node_id: 'MAUROPRIME', node_role: 'primary', node_platform: 'windows' },
    { id: 'tele_abc', name: 'Telegram chat', count: 3, last_str: '2026-06-16T09:00:00Z', node_id: 'MAUROPRIME', node_role: 'primary', node_platform: 'windows' },
    { id: 'sess_003', name: 'Research', count: 12, last_str: '2026-06-15T18:00:00Z', node_id: 'archlinux', node_role: 'secondary', node_platform: 'linux' },
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

  it('renders compact platform and role icons without node text', () => {
    sessionList.renderSessions(sessions, 'sess_001');
    const item = sidebarEl.querySelector('.session-item[data-sid="sess_003"]');
    const origin = item!.querySelector('.session-origin');
    expect(origin).not.toBeNull();
    expect(origin!.textContent).toBe('');
    expect(origin!.querySelector('img[src="/static/icons/node-linux.svg"]')).not.toBeNull();
    expect(origin!.querySelector('img[src="/static/icons/node-secondary.svg"]')).not.toBeNull();
    expect(origin!.getAttribute('title')).toContain('archlinux');
  });

  it.each([
    ['windows', 'primary'],
    ['windows', 'secondary'],
    ['linux', 'primary'],
    ['linux', 'secondary'],
  ])('renders the correct DOM icons for %s %s', (platform, role) => {
    sessionList.renderSessions([{
      id: `session-${platform}-${role}`,
      name: 'Node session',
      node_id: `node-${platform}`,
      node_platform: platform,
      node_role: role,
    }], '');

    const origin = sidebarEl.querySelector('.session-origin')!;
    const icons = Array.from(origin.querySelectorAll('img'));
    expect(icons).toHaveLength(2);
    expect(icons[0].getAttribute('src')).toBe(`/static/icons/node-${platform}.svg`);
    expect(icons[1].getAttribute('src')).toBe(`/static/icons/node-${role}.svg`);
    expect(origin.getAttribute('title')).toContain(platform);
    expect(origin.getAttribute('title')).toContain(role);
  });

  it('omits an unknown platform icon and keeps the safe secondary role icon', () => {
    sessionList.renderSessions([{
      id: 'session-unknown-node',
      name: 'Unknown node',
      node_id: 'mystery-node',
      node_platform: 'plan9',
      node_role: 'unexpected',
    }], '');

    const icons = sidebarEl.querySelectorAll('.session-origin img');
    expect(icons).toHaveLength(1);
    expect(icons[0].getAttribute('src')).toBe('/static/icons/node-secondary.svg');
  });

  it('has session-meta with message count', () => {
    sessionList.renderSessions(sessions, 'sess_001');
    const item = sidebarEl.querySelector('.session-item[data-sid="sess_001"]');
    const meta = item!.querySelector('.session-meta');
    expect(meta!.textContent).toContain('5 exchanges');
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
