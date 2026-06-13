import { mergeFloat32Chunks } from './pcm-utils.js';

const DEFAULTS = {
  frameSize: 1024,
  speechThreshold: 0.018,
  silenceThreshold: 0.01,
  startSilenceFrames: 2,
  endSilenceMs: 420,
  maxSegmentMs: 3500,
  preRollMs: 220,
  overlapMs: 180,
  minSegmentMs: 300,
};

export class VadSegmenter {
  constructor(sampleRate, options = {}) {
    this.sampleRate = sampleRate;
    this.options = { ...DEFAULTS, ...options };
    this._frameSize = this.options.frameSize;
    this._frameMs = (this._frameSize / sampleRate) * 1000;
    this._active = false;
    this._silenceFrames = 0;
    this._current = [];
    this._currentSamples = 0;
    this._preRoll = [];
    this._preRollSamples = 0;
    this._carry = new Float32Array(0);
  }

  push(input) {
    const out = [];
    if (!input || input.length === 0) {
      return out;
    }
    const merged = this._appendCarry(input);
    for (let offset = 0; offset + this._frameSize <= merged.length; offset += this._frameSize) {
      const frame = merged.subarray(offset, offset + this._frameSize);
      const rms = rootMeanSquare(frame);
      const emitted = this._ingestFrame(frame, rms);
      if (emitted.length > 0) {
        out.push(...emitted);
      }
    }
    const remainder = merged.length % this._frameSize;
    this._carry = remainder > 0 ? merged.slice(merged.length - remainder) : new Float32Array(0);
    return out;
  }

  flush() {
    const out = [];
    if (this._active && this._currentSamples > 0) {
      const emitted = this._emitCurrent(false);
      if (emitted.samples.length >= this._minSegmentSamples()) {
        out.push(emitted);
      }
    }
    this._reset(false);
    this._carry = new Float32Array(0);
    return out;
  }

  _appendCarry(input) {
    if (!this._carry.length) return input;
    const merged = new Float32Array(this._carry.length + input.length);
    merged.set(this._carry, 0);
    merged.set(input, this._carry.length);
    return merged;
  }

  _ingestFrame(frame, rms) {
    const out = [];
    const speech = rms >= this.options.speechThreshold;
    const idleVoice = rms >= this.options.silenceThreshold;
    this._rememberPreRoll(frame);

    if (!this._active) {
      if (speech) {
        this._active = true;
        this._silenceFrames = 0;
        this._current = this._preRoll.slice();
        this._currentSamples = this._current.reduce((sum, part) => sum + part.length, 0);
        this._pushCurrent(frame);
      }
      return out;
    }

    this._pushCurrent(frame);

    if (speech) {
      this._silenceFrames = 0;
    } else if (!idleVoice) {
      this._silenceFrames += 1;
    } else {
      this._silenceFrames = Math.max(0, this._silenceFrames - 1);
    }

    const elapsedMs = (this._currentSamples / this.sampleRate) * 1000;
    const shouldFlushBySilence = this._silenceFrames * this._frameMs >= this.options.endSilenceMs;
    const shouldFlushByLength = elapsedMs >= this.options.maxSegmentMs;

    if (shouldFlushBySilence || shouldFlushByLength) {
      if (this._currentSamples >= this._minSegmentSamples()) {
        const emitted = this._emitCurrent(shouldFlushByLength);
        out.push(emitted);
      } else {
        this._reset(false);
      }
    }

    return out;
  }

  _pushCurrent(frame) {
    this._current.push(new Float32Array(frame));
    this._currentSamples += frame.length;
  }

  _emitCurrent(keepTail) {
    const flat = mergeFloat32Chunks(this._current, this._currentSamples);
    const overlapSamples = keepTail ? Math.min(flat.length, Math.round((this.options.overlapMs / 1000) * this.sampleRate)) : 0;
    const emitEnd = overlapSamples > 0 ? flat.length - overlapSamples : flat.length;
    const emitted = flat.slice(0, Math.max(0, emitEnd));
    const tail = overlapSamples > 0 ? flat.slice(flat.length - overlapSamples) : new Float32Array(0);
    this._reset(false);
    if (tail.length > 0) {
      this._current = [tail];
      this._currentSamples = tail.length;
      this._active = true;
    }
    return { samples: emitted, sampleRate: this.sampleRate };
  }

  _rememberPreRoll(frame) {
    const maxSamples = Math.round((this.options.preRollMs / 1000) * this.sampleRate);
    this._preRoll.push(new Float32Array(frame));
    this._preRollSamples += frame.length;
    while (this._preRollSamples > maxSamples && this._preRoll.length > 0) {
      const dropped = this._preRoll.shift();
      this._preRollSamples -= dropped.length;
    }
  }

  _reset(clearPreRoll) {
    this._active = false;
    this._silenceFrames = 0;
    this._current = [];
    this._currentSamples = 0;
    if (clearPreRoll) {
      this._preRoll = [];
      this._preRollSamples = 0;
    }
  }

  _minSegmentSamples() {
    return Math.round((this.options.minSegmentMs / 1000) * this.sampleRate);
  }
}

function rootMeanSquare(frame) {
  let sum = 0;
  for (let i = 0; i < frame.length; i++) {
    const sample = frame[i];
    sum += sample * sample;
  }
  return Math.sqrt(sum / Math.max(1, frame.length));
}
