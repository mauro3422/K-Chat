import { describe, it, expect } from 'vitest';
import { C } from '../core/infra/DomContracts';

describe('DomContracts — CSS class constants', () => {
  it('MSG_BODY is msg-body', () => {
    expect(C.MSG_BODY).toBe('msg-body');
  });

  it('LIVE_MSG is live-msg', () => {
    expect(C.LIVE_MSG).toBe('live-msg');
  });

  it('REASONING is reasoning', () => {
    expect(C.REASONING).toBe('reasoning');
  });

  it('TOOL_CALLS is tool-calls', () => {
    expect(C.TOOL_CALLS).toBe('tool-calls');
  });

  it('TC_ITEM is tc-item', () => {
    expect(C.TC_ITEM).toBe('tc-item');
  });

  it('TC_ITEM_OK is tc-item ok', () => {
    expect(C.TC_ITEM_OK).toBe('tc-item ok');
  });

  it('TC_ITEM_ERROR is tc-item error', () => {
    expect(C.TC_ITEM_ERROR).toBe('tc-item error');
  });

  it('TC_ITEM_CALLING is tc-item calling', () => {
    expect(C.TC_ITEM_CALLING).toBe('tc-item calling');
  });

  it('ERROR_CARD is error-card', () => {
    expect(C.ERROR_CARD).toBe('error-card');
  });

  it('RATE_LIMIT_CARD is rate-limit-card', () => {
    expect(C.RATE_LIMIT_CARD).toBe('rate-limit-card');
  });

  it('WIDGET_CONTAINER is interactive-widget-container', () => {
    expect(C.WIDGET_CONTAINER).toBe('interactive-widget-container');
  });

  it('WIDGET_IFRAME is widget-iframe', () => {
    expect(C.WIDGET_IFRAME).toBe('widget-iframe');
  });

  it('MSG_LABEL is msg-label', () => {
    expect(C.MSG_LABEL).toBe('msg-label');
  });

  it('MSG_TS is msg-ts', () => {
    expect(C.MSG_TS).toBe('msg-ts');
  });

  it('MSG_DELETE_BTN is msg-delete-btn', () => {
    expect(C.MSG_DELETE_BTN).toBe('msg-delete-btn');
  });

  it('MSG_TEXT_SEGMENT is msg-text-segment', () => {
    expect(C.MSG_TEXT_SEGMENT).toBe('msg-text-segment');
  });

  it('STREAMING is streaming', () => {
    expect(C.STREAMING).toBe('streaming');
  });

  it('REASONING_MEMORIES has both classes', () => {
    expect(C.REASONING_MEMORIES).toBe('reasoning memories-phase');
  });

  it('RT is rt', () => {
    expect(C.RT).toBe('rt');
  });

  it('MEMORY_CONTENT has both classes', () => {
    expect(C.MEMORY_CONTENT).toBe('rt memory-content');
  });

  it('ERROR_HEADER is error-header', () => {
    expect(C.ERROR_HEADER).toBe('error-header');
  });

  it('ERROR_DETAIL is error-detail', () => {
    expect(C.ERROR_DETAIL).toBe('error-detail');
  });

  it('ERROR_HINT is error-hint', () => {
    expect(C.ERROR_HINT).toBe('error-hint');
  });

  it('RETRY_BTN is error-retry-btn', () => {
    expect(C.RETRY_BTN).toBe('error-retry-btn');
  });

  it('WIDGET_PLACEHOLDER is widget-placeholder', () => {
    expect(C.WIDGET_PLACEHOLDER).toBe('widget-placeholder');
  });

  it('WIDGET_LOADING is widget-loading', () => {
    expect(C.WIDGET_LOADING).toBe('widget-loading');
  });

  it('WIDGET_ERROR is widget-error', () => {
    expect(C.WIDGET_ERROR).toBe('widget-error');
  });

  it('WIDGET_TOOLBAR is widget-toolbar', () => {
    expect(C.WIDGET_TOOLBAR).toBe('widget-toolbar');
  });

  it('EMPTY_STATE is empty-state', () => {
    expect(C.EMPTY_STATE).toBe('empty-state');
  });

  it('MD_CONTENT is md-content', () => {
    expect(C.MD_CONTENT).toBe('md-content');
  });

  it('all constants defined', () => {
    expect(Object.keys(C).length).toBeGreaterThanOrEqual(25);
  });
});
