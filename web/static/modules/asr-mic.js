/**
 * ASR Mic Button — speech-to-text via Web Speech API, fallback Google ASR backend.
 *
 * Web Speech first (browser-native, live dictation).
 * If result is too short, tries getUserMedia + backend /api/asr/transcribe.
 *
 * Text input grows automatically with content (textarea behavior).
 * No auto-restart on user stop.
 *
 * Survives HTMX via event delegation on document.
 */

(function () {
  var log = console.log.bind(console, '[ASR]');
  var C = { IDLE: 'asr-mic-idle', RECORDING: 'asr-mic-recording', TRANSCRIBING: 'asr-mic-transcribing' };

  var state = C.IDLE;
  var recognition = null;
  var finalText = '';
  var recognizedChunks = [];
  var userStopped = false;  // Prevents auto-restart

  function btn() { return document.getElementById('asr-mic-btn'); }
  function inp() { return document.getElementById('msg-input'); }
  function has(cls) { var b = btn(); return b && b.classList.contains(cls); }

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
    i.style.height = i.scrollHeight + 'px';
    i.dispatchEvent(new Event('input', { bubbles: true }));
  }

  document.addEventListener('click', function (e) {
    var b = e.target.closest('#asr-mic-btn');
    if (!b) return;
    if (state === C.IDLE) start();
    else if (state === C.RECORDING) stop();
  });

  // ── Start ──
  function start() {
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { toast('❌ Dictado no soportado'); return; }

    finalText = '';
    recognizedChunks = [];
    userStopped = false;
    setInput('');
    setState(C.RECORDING);
    resizeInput();
    toast('🎤 Hablá — texto aparece solo');

    recognition = new SR();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'es-AR';
    recognition.maxAlternatives = 1;

    recognition.onresult = function (event) {
      var interim = '';
      for (var idx = event.resultIndex; idx < event.results.length; idx++) {
        var r = event.results[idx];
        if (r.isFinal) {
          var t = r[0].transcript.trim();
          if (t.length > 1 && recognizedChunks.indexOf(t) === -1) {
            recognizedChunks.push(t);
            finalText += (finalText ? ' ' : '') + t;
          }
        } else {
          interim = r[0].transcript;
        }
      }
      var display = '🎤 ' + finalText;
      if (interim) display += ' ' + interim;
      setInput(display);
      resizeInput();
    };

    recognition.onerror = function (e) {
      log('WebSpeech error:', e.error);
      if (e.error === 'not-allowed') { toast('❌ Permití el micrófono'); cleanup(); }
    };

    recognition.onend = function () {
      log('WebSpeech ended (final=%d chars, userStopped=%s)', finalText.length, userStopped);
      // Only restart if user didn't explicitly stop AND text is still short
      if (!userStopped && state === C.RECORDING && finalText.length < 3) {
        log('Auto-restarting…');
        try { recognition.start(); } catch (e) { log('Restart failed'); }
      }
    };

    try { recognition.start(); log('WebSpeech started'); }
    catch (e) { log('Failed:', e.message); toast('❌ Error: ' + e.message); cleanup(); }
  }

  // ── Stop ──
  function stop() {
    userStopped = true;
    if (recognition) {
      try { recognition.stop(); } catch (e) {}
      recognition = null;
    }

    if (finalText && finalText.length >= 3) {
      setInput('🎤 ' + finalText);
      resizeInput();
      toast('✅');
      setState(C.IDLE);
      return;
    }

    // Text too short — try backend
    setState(C.TRANSCRIBING, true);
    toast('Grabando para Google ASR…');
    tryBackend();
  }

  // ── Backend fallback ──
  async function tryBackend() {
    var stream = null, recorder = null, chunks = [];
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (err) { toast('❌ Micrófono no disponible'); cleanup(); return; }

    var mime = 'audio/webm;codecs=opus';
    if (!MediaRecorder.isTypeSupported(mime)) mime = 'audio/webm';
    recorder = new MediaRecorder(stream, { mimeType: mime });
    recorder.ondataavailable = function (e) { if (e.data.size > 0) chunks.push(e.data); };
    recorder.onstop = async function () {
      if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
      if (chunks.length === 0) { cleanup(); return; }
      var blob = new Blob(chunks, { type: 'audio/webm' });
      log('Backend: %d bytes', blob.size);
      try {
        var res = await fetch('/api/asr/transcribe', { method: 'POST', headers: { 'Content-Type': 'audio/webm' }, body: blob });
        var data = await res.json();
        if (data.success && data.transcript) {
          setInput('🎤 ' + data.transcript);
          resizeInput();
          toast('✅ (Google ASR)');
        } else { toast('❌ ' + (data.error || 'Error')); }
      } catch (err) { toast('❌ Error de conexión'); }
      cleanup();
    };
    recorder.start();
  }

  function resizeInput() {
    var i = inp();
    if (!i) return;
    i.style.height = 'auto';
    i.style.height = Math.max(40, i.scrollHeight) + 'px';
  }

  function cleanup() {
    setState(C.IDLE);
    finalText = '';
    recognizedChunks = [];
    userStopped = false;
  }

  function toast(msg) {
    if (window.KairosUtils && typeof window.KairosUtils.showToast === 'function') {
      window.KairosUtils.showToast(msg);
    } else {
      var t = document.createElement('div');
      t.textContent = msg;
      t.style.cssText = 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:8px 16px;border-radius:8px;z-index:9999;font-size:14px;transition:opacity 0.3s;';
      document.body.appendChild(t);
      setTimeout(function () {
        t.style.opacity = '0';
        setTimeout(function () { try { if (t.parentNode) t.parentNode.removeChild(t); } catch (e) {} }, 300);
      }, 2500);
    }
  }

  log('ASR ready — live Web Speech with growing input');
})();
