import { describe, test, expect } from 'vitest';
import './setup.js';
import {
  STREAM_EVENT_TYPES,
  parseStreamEvent,
  serializeStreamEvent,
} from '../web/static/modules/stream-contract.js';

describe('stream contract', () => {
  test('defines the canonical stream event types', () => {
    expect(STREAM_EVENT_TYPES).toEqual({
      HEARTBEAT: 'heartbeat',
      CONTENT: 'content',
      REASONING: 'reasoning',
      TOOL_CALL: 'tool_call',
      ERROR: 'error',
    });
  });

  test('parses valid event lines', () => {
    expect(parseStreamEvent('{"t":"content","d":"hola"}')).toEqual({ t: 'content', d: 'hola' });
  });

  test('rejects unknown event types', () => {
    expect(parseStreamEvent('{"t":"weird","d":"x"}')).toBe(null);
  });

  test('serializes valid events', () => {
    expect(serializeStreamEvent('heartbeat', '')).toBe('{"t":"heartbeat","d":""}\n');
  });
});
