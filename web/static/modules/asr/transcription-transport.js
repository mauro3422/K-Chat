export class AsrTranscriptionTransport {
  constructor(sessionId) {
    this.socket = null;
    this.readyPromise = null;
    this.pending = [];
    this.useWebSocket = typeof WebSocket !== 'undefined';
    this.closed = false;
    this.sessionId = sessionId || '';
  }

  async connect() {
    if (!this.useWebSocket) return false;
    if (this.socket && this.socket.readyState === WebSocket.OPEN) return true;
    if (this.readyPromise) return this.readyPromise;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    let url = protocol + '//' + window.location.host + '/api/asr/stream';
    if (this.sessionId) {
      url += '?session_id=' + encodeURIComponent(this.sessionId);
    }

    this.readyPromise = new Promise((resolve) => {
      let settled = false;
      try {
        this.socket = new WebSocket(url);
      } catch (err) {
        this.readyPromise = null;
        resolve(false);
        return;
      }

      this.socket.binaryType = 'arraybuffer';
      this.socket.onopen = () => {
        settled = true;
        this.readyPromise = null;
        resolve(true);
      };
      this.socket.onmessage = (event) => {
        this._handleMessage(event.data);
      };
      this.socket.onerror = () => {
        if (!settled) {
          this.readyPromise = null;
          resolve(false);
        }
      };
      this.socket.onclose = () => {
        this.socket = null;
        if (this.pending.length > 0) {
          this._flushPendingFailure('ASR websocket closed');
        }
        if (!settled) {
          this.readyPromise = null;
          resolve(false);
        }
      };
    });

    return this.readyPromise;
  }

  async transcribe(audioBlob) {
    if (await this.connect()) {
      return this._transcribeViaSocket(audioBlob);
    }
    return {
      success: false,
      error: 'ASR websocket unavailable',
      transport: 'ws',
    };
  }

  async close() {
    this.closed = true;
    this._flushPendingFailure('ASR transport closed');
    if (!this.socket) return;
    try {
      this.socket.send('close');
    } catch (err) {}
    try {
      this.socket.close();
    } catch (err) {}
    this.socket = null;
  }

  async _transcribeViaSocket(audioBlob) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return {
        success: false,
        error: 'ASR websocket unavailable',
        transport: 'ws',
      };
    }

    const payload = await audioBlob.arrayBuffer();
    return new Promise((resolve) => {
      this.pending.push(resolve);
      try {
        this.socket.send(payload);
      } catch (err) {
        this.pending.pop();
        resolve({
          success: false,
          error: err && err.message ? err.message : String(err),
          transport: 'ws',
        });
      }
    });
  }

  _handleMessage(raw) {
    let data = raw;
    if (typeof raw === 'string') {
      try {
        data = JSON.parse(raw);
      } catch (err) {
        return;
      }
    }

    if (!data || data.type === 'ready') {
      return;
    }

    if (data.type !== 'transcript') {
      return;
    }

    const resolve = this.pending.shift();
    if (resolve) {
      resolve({ ...data, transport: 'ws' });
    }
  }

  _flushPendingFailure(error) {
    if (!this.pending.length) {
      return;
    }
    const pending = this.pending.splice(0, this.pending.length);
    for (let i = 0; i < pending.length; i += 1) {
      pending[i]({
        success: false,
        error: error,
      });
    }
  }
}
