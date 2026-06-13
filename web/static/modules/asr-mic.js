/**
 * ASR Mic Button — chunked speech-to-text via getUserMedia + Google Speech API.
 *
 * No Web Speech API.
 * 4-second chunks sent to /api/asr/transcribe.
 * Text accumulates, never shrinks, never flickers.
 *
 * Survives HTMX via event delegation.
 */

(function () {
  var log = console.log.bind(console, '[ASR]');
  var C = { IDLE: 'asr-mic-idle', RECORDING: 'asr-mic-recording', TRANSCRIBING: 'asr-mic-transcribing' };

  var state = C.IDLE;
  var stream = null;
  var recorder = null;
  var accumulatedText = '';
  var pendingChunks = 0;    // Chunks still being processed
  var stopped = false;       // User requested stop

  var CHUNK_MS = 4000;      // 4 seconds per chunk

  function btn() { return document.getElementById('asr-mic-btn'); }
  function inp() { return document.getElementById('msg-input'); }

  function setState(cls, disabled) {
    state = cls;
    var b = btn(); if (!b) return;
    b.className = cls; b.disabled = !!disabled;
    b.textContent = cls === C.IDLE ? '🎤' : cls === C.RECORDING ? '⏹️' : '⏳';
  }

  function setInput(val) {
    var i = inp();
    if (!i) return;
    i.value = val;
    i.style.height = 'auto';
    var h = Math.min(Math.max(42, i.scrollHeight), 300);
    i.style.height = h + 'px';
    i.style.overflowY = h >= 300 ? 'auto' : 'hidden';
    i.dispatchEvent(new Event('input', { bubbles: true }));
  }

  document.addEventListener('click', function (e) {
    var b = e.target.closest('#asr-mic-btn');
    if (!b) return;
    if (state === C.IDLE) start();
    else if (state === C.RECORDING) stop();
  });

  // ── Start ──
  async function start() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      log('Mic denied:', err.message);
      toast('❌ Necesito acceso al micrófono');
      return;
    }

    accumulatedText = '';
    pendingChunks = 0;
    stopped = false;
    var i = inp(); if (i) { i.value = ''; i.style.height = '42px'; }
    setState(C.RECORDING);
    toast('🎤 Grabando…');

    var mime = 'audio/webm;codecs=opus';
    if (!MediaRecorder.isTypeSupported(mime)) mime = 'audio/webm';

    recorder = new MediaRecorder(stream, { mimeType: mime });

    recorder.ondataavailable = function (e) {
      if (e.data.size > 0) {
        var chunk = e.data;
        pendingChunks++;
        // Fire and forget — each chunk sends independently
        sendChunk(chunk);
      }
    };

    recorder.onstop = function () {
      log('Recorder stopped, pending=%d', pendingChunks);
      if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
      recorder = null;
    };

    recorder.onerror = function () {
      log('Recorder error');
      toast('❌ Error grabando');
      cleanup();
    };

    // Fire ondataavailable every CHUNK_MS with that chunk's data
    recorder.start(CHUNK_MS);
    log('Recording started (chunks every %dms)', CHUNK_MS);
  }

  // ── Send one chunk ──
  async function sendChunk(audioBlob) {
    log('Sending chunk (%d bytes, pending=%d)', audioBlob.size, pendingChunks);

    try {
      var res = await fetch('/api/asr/transcribe', {
        method: 'POST',
        headers: { 'Content-Type': 'audio/webm' },
        body: audioBlob
      });
      var data = await res.json();

      if (data.success && data.transcript) {
        var text = data.transcript.trim();
        if (text.length > 1) {
          accumulatedText += (accumulatedText ? ' ' : '') + text;
          setInput('🎤 ' + accumulatedText);
          log('Chunk ok: %s', text.substring(0, 60));
        }
      } else {
        log('Chunk fail:', data.error);
      }
    } catch (err) {
      log('Chunk error:', err.message);
    } finally {
      pendingChunks--;
      log('Chunk done, pending=%d, stopped=%s', pendingChunks, stopped);
      // If user stopped and all chunks processed → finalize
      if (stopped && pendingChunks <= 0) {
        finalizeResult();
      }
    }
  }

  // ── Stop ──
  function stop() {
    if (!recorder || recorder.state !== 'recording') return;
    stopped = true;
    setState(C.TRANSCRIBING, true);
    recorder.stop();
    log('Stop requested');
    // Safety: if no chunks were in flight, finalize after a short timeout
    setTimeout(function () {
      if (pendingChunks <= 0) finalizeResult();
    }, 8000);
  }

  // ── Finalize ──
  function finalizeResult() {
    if (accumulatedText && accumulatedText.length >= 2) {
      setInput('🎤 ' + accumulatedText);
      toast('✅');
    } else {
      toast('ℹ️ No se grabó bien');
    }
    setState(C.IDLE);
    pendingChunks = 0;
    log('Finalized: %d chars', accumulatedText.length);
  }

  function cleanup() {
    if (recorder && recorder.state === 'recording') { try { recorder.stop(); } catch (e) {} }
    if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
    recorder = null;
    accumulatedText = '';
    pendingChunks = 0;
    stopped = false;
    setState(C.IDLE);
  }

  function toast(msg) {
    var t = document.createElement('div');
    t.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:8px 16px;border-radius:4px;z-index:9999;font-size:14px;';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function(){ t.remove(); }, 3000);
  }

  log('ASR ready — chunked (4s)');
})();
