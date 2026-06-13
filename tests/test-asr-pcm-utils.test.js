import { describe, expect, test } from 'vitest';
import { encodeWav, mergeFloat32Chunks } from '../web/static/modules/asr/pcm-utils.js';

describe('ASR PCM utils', () => {
  test('mergeFloat32Chunks concatenates samples', () => {
    const merged = mergeFloat32Chunks([new Float32Array([0.1, 0.2]), new Float32Array([0.3])], 3);
    expect(merged).toHaveLength(3);
    expect(merged[0]).toBeCloseTo(0.1, 6);
    expect(merged[1]).toBeCloseTo(0.2, 6);
    expect(merged[2]).toBeCloseTo(0.3, 6);
  });

  test('encodeWav writes a valid RIFF header', async () => {
    const blob = encodeWav(new Float32Array([0, 0.5, -0.5]), 16000);
    expect(blob.type).toBe('audio/wav');

    const buffer = await blob.arrayBuffer();
    const view = new DataView(buffer);
    expect(String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3))).toBe('RIFF');
    expect(String.fromCharCode(view.getUint8(8), view.getUint8(9), view.getUint8(10), view.getUint8(11))).toBe('WAVE');
    expect(view.getUint32(24, true)).toBe(16000);
  });
});
