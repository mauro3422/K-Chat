import { describe, expect, test } from 'vitest';
import { mergeTranscript, punctuateTranscript, collapseAdjacentTokens } from '../web/static/modules/asr/transcript-utils.js';

describe('ASR transcript utils', () => {
  test('mergeTranscript removes overlap at the segment boundary', () => {
    const merged = mergeTranscript('hola qué onda', 'onda cómo va');
    expect(merged).toBe('hola qué onda cómo va');
  });

  test('mergeTranscript keeps non-overlapping incoming text', () => {
    const merged = mergeTranscript('hola', 'mundo');
    expect(merged).toBe('hola mundo');
  });

  test('collapseAdjacentTokens limits repeated tokens', () => {
    expect(collapseAdjacentTokens(['sí', 'sí', 'sí', 'sí', 'vale'])).toEqual(['sí', 'sí', 'vale']);
  });

  test('punctuateTranscript appends punctuation conservatively', () => {
    expect(punctuateTranscript('hola qué onda', 'algo', 2400, 0)).toBe('hola qué onda.');
    expect(punctuateTranscript('hola qué onda', 'algo', 900, 800)).toBe('hola qué onda,');
  });
});

