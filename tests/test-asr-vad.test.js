import { describe, expect, test } from 'vitest';
import { VadSegmenter } from '../web/static/modules/asr/vad.js';

function speechFrame(value, length = 10) {
  return new Float32Array(length).fill(value);
}

describe('ASR VAD segmenter', () => {
  test('emits a segment after speech followed by silence', () => {
    const segmenter = new VadSegmenter(1000, {
      frameSize: 10,
      speechThreshold: 0.1,
      silenceThreshold: 0.05,
      endSilenceMs: 20,
      maxSegmentMs: 100,
      preRollMs: 10,
      overlapMs: 0,
      minSegmentMs: 10,
    });

    expect(segmenter.push(speechFrame(0.2, 20))).toEqual([]);

    const emitted = segmenter.push(speechFrame(0, 20));
    expect(emitted).toHaveLength(1);
    expect(emitted[0].sampleRate).toBe(1000);
    expect(emitted[0].samples.length).toBeGreaterThan(0);
  });

  test('flush emits the remaining active segment', () => {
    const segmenter = new VadSegmenter(1000, {
      frameSize: 10,
      speechThreshold: 0.1,
      silenceThreshold: 0.05,
      endSilenceMs: 100,
      maxSegmentMs: 1000,
      preRollMs: 10,
      overlapMs: 0,
      minSegmentMs: 10,
    });

    segmenter.push(speechFrame(0.2, 10));
    const emitted = segmenter.flush();
    expect(emitted).toHaveLength(1);
    expect(emitted[0].samples.length).toBeGreaterThan(0);
  });
});
