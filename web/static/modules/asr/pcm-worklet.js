class AsrPcmProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Float32Array(0);
    this._targetSamples = 2048;
  }

  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input || input.length === 0) return true;

    const merged = new Float32Array(this._buffer.length + input.length);
    merged.set(this._buffer, 0);
    merged.set(input, this._buffer.length);

    let offset = 0;
    while (merged.length - offset >= this._targetSamples) {
      const chunk = merged.slice(offset, offset + this._targetSamples);
      this.port.postMessage({ type: 'pcm', samples: chunk }, [chunk.buffer]);
      offset += this._targetSamples;
    }

    this._buffer = merged.slice(offset);
    return true;
  }
}

registerProcessor('asr-pcm-processor', AsrPcmProcessor);
