export class AudioCapture {
  constructor(onPcmChunk) {
    this.onPcmChunk = onPcmChunk;
    this.stream = null;
    this.audioContext = null;
    this.sourceNode = null;
    this.workletNode = null;
  }

  async start(stream) {
    this.stream = stream;
    this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
    await this.audioContext.audioWorklet.addModule('/static/modules/asr/pcm-worklet.js');
    this.sourceNode = this.audioContext.createMediaStreamSource(stream);
    this.workletNode = new AudioWorkletNode(this.audioContext, 'asr-pcm-processor');
    this.workletNode.port.onmessage = (event) => {
      if (event.data && event.data.type === 'pcm' && event.data.samples) {
        this.onPcmChunk(event.data.samples, this.audioContext.sampleRate);
      }
    };
    this.sourceNode.connect(this.workletNode);
    this.workletNode.connect(this.audioContext.destination);
    await this.audioContext.resume();
    return this.audioContext.sampleRate;
  }

  async stop() {
    if (this.sourceNode) {
      try { this.sourceNode.disconnect(); } catch (e) {}
      this.sourceNode = null;
    }
    if (this.workletNode) {
      try { this.workletNode.disconnect(); } catch (e) {}
      this.workletNode.port.onmessage = null;
      this.workletNode = null;
    }
    if (this.audioContext) {
      try { await this.audioContext.close(); } catch (e) {}
      this.audioContext = null;
    }
    if (this.stream) {
      this.stream.getTracks().forEach(function (track) { track.stop(); });
      this.stream = null;
    }
  }
}
