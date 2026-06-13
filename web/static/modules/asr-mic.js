/**
 * ASR Mic Button
 *
 * Orchestrates mic capture, VAD segmentation, WAV encoding and live ASR reveal.
 * Low-level audio capture lives in ./asr/audio-capture.js.
 */

import { AudioCapture } from './asr/audio-capture.js';
import { VadSegmenter } from './asr/vad.js';
import { encodeWav } from './asr/pcm-utils.js';
import { AsrTranscriptionTransport } from './asr/transcription-transport.js';
import { appendAsrTelemetry, setAsrVisibleText } from './asr/contract.js';
import { mergeTranscript, punctuateTranscript, splitTokens } from './asr/transcript-utils.js';
import { SessionContext } from './session-context.js';

const log = console.log.bind(console, '[ASR]');
const C = { IDLE: 'asr-mic-idle', RECORDING: 'asr-mic-recording', TRANSCRIBING: 'asr-mic-transcribing' };

const SEGMENT_OPTIONS = {
  frameSize: 1024,
  speechThreshold: 0.018,
  silenceThreshold: 0.01,
  startSilenceFrames: 2,
  endSilenceMs: 200,
  maxSegmentMs: 2800,
  preRollMs: 160,
  overlapMs: 120,
  minSegmentMs: 180,
};

const BOOTSTRAP_SEGMENT_OPTIONS = {
  frameSize: 1024,
  speechThreshold: 0.018,
  silenceThreshold: 0.01,
  startSilenceFrames: 1,
  endSilenceMs: 120,
  maxSegmentMs: 1100,
  preRollMs: 100,
  overlapMs: 80,
  minSegmentMs: 120,
};

let state = C.IDLE;
let accumulatedText = '';
let capture = null;
let segmenter = null;
let transport = null;
let queue = [];
let sending = false;
let pendingSegments = 0;
let stopRequested = false;
let segmentMode = 'bootstrap';
let revealTimer = null;
let visibleText = '';
let lastSuccessAtMs = 0;

function btn() { return document.getElementById('asr-mic-btn'); }
function inp() { return document.getElementById('msg-input'); }

function recordAsrTelemetry(event) {
  appendAsrTelemetry(event);
}

function setState(cls, disabled) {
  state = cls;
  const b = btn();
  if (!b) return;
  b.className = cls;
  b.disabled = !!disabled;
  b.textContent = cls === C.IDLE ? '🎤' : cls === C.RECORDING ? '⏹️' : '⏳';
}

function setInput(val) {
  const i = inp();
  if (!i) return;
  i.value = val;
  i.style.height = 'auto';
  const h = Math.min(Math.max(42, i.scrollHeight), 300);
  i.style.height = h + 'px';
  i.style.overflowY = h >= 300 ? 'auto' : 'hidden';
  i.dispatchEvent(new Event('input', { bubbles: true }));
}

document.addEventListener('click', function (e) {
  const b = e.target.closest('#asr-mic-btn');
  if (!b) return;
  if (state === C.IDLE) start();
  else if (state === C.RECORDING) stop();
});

async function start() {
  let stream = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    accumulatedText = '';
    visibleText = '';
    queue = [];
    sending = false;
    pendingSegments = 0;
    stopRequested = false;
    segmentMode = 'bootstrap';
    stopRevealTimer();
    lastSuccessAtMs = 0;
    setAsrVisibleText('');
    transport = new AsrTranscriptionTransport(SessionContext.getSessionId());
    const i = inp();
    if (i) {
      i.value = '';
      i.style.height = '42px';
    }

    capture = new AudioCapture(onPcmChunk);
    const sampleRate = await capture.start(stream);
    segmenter = new VadSegmenter(sampleRate, SEGMENT_OPTIONS);
    applySegmentMode('bootstrap');
    setState(C.RECORDING);
    toast('🎤 Grabando...');
    log('Recording started at %d Hz', sampleRate);
  } catch (err) {
    log('Mic start failed:', err && err.message ? err.message : String(err));
    if (stream) {
      stream.getTracks().forEach(function (track) { track.stop(); });
    }
    toast('❌ Necesito acceso al micrófono');
    await cleanup();
  }
}

function onPcmChunk(samples, sampleRate) {
  if (!segmenter || !samples || samples.length === 0) return;
  const segments = segmenter.push(samples, sampleRate);
  if (segments.length > 0) {
    enqueueSegments(segments);
  }
}

function enqueueSegments(segments) {
  if (!segments || segments.length === 0) return;
  queue.push(...segments);
  drainQueue();
}

function drainQueue() {
  if (sending) return;
  const segment = queue.shift();
  if (!segment) {
    if (stopRequested && pendingSegments === 0) {
      finalizeResult();
    }
    return;
  }

  sending = true;
  pendingSegments += 1;
  const audioBlob = encodeWav(segment.samples, segment.sampleRate);
  const segmentDurationMs = Math.round((segment.samples.length / segment.sampleRate) * 1000);
  const receivedAtMs = Date.now();
  log('Sending segment (%d bytes, pending=%d)', audioBlob.size, pendingSegments);

  transport.transcribe(audioBlob)
    .then(function (data) {
      const gapMs = lastSuccessAtMs > 0 ? Math.max(0, receivedAtMs - lastSuccessAtMs) : 0;
      recordAsrTelemetry({
        session_id: SessionContext.getSessionId(),
        transport: data && data.transport ? data.transport : 'unknown',
        bytes: audioBlob.size,
        sample_rate: segment.sampleRate,
        duration_ms: segmentDurationMs,
        gap_ms: gapMs,
        success: !!(data && data.success),
        transcript: data && data.transcript ? data.transcript : '',
        error: data && data.error ? data.error : '',
      });
      if (data && data.success && data.transcript) {
        const transcript = data.transcript.trim();
        if (transcript.length > 1) {
          const merged = mergeTranscript(accumulatedText, transcript);
          accumulatedText = punctuateTranscript(merged, transcript, segmentDurationMs, gapMs);
          lastSuccessAtMs = Date.now();
          revealTranscript(accumulatedText);
          if (segmentMode === 'bootstrap') {
            applySegmentMode('normal');
            segmentMode = 'normal';
          }
          log('Segment ok: %s', accumulatedText.substring(Math.max(0, accumulatedText.length - 80)));
        }
      } else {
        log('Segment fail:', data && data.error ? data.error : 'unknown error');
      }
    })
    .catch(function (err) {
      recordAsrTelemetry({
        session_id: SessionContext.getSessionId(),
        transport: 'unknown',
        bytes: audioBlob.size,
        sample_rate: segment.sampleRate,
        success: false,
        error: err && err.message ? err.message : String(err),
      });
      log('Segment error:', err && err.message ? err.message : String(err));
    })
    .finally(function () {
      pendingSegments -= 1;
      sending = false;
      log('Segment done, pending=%d, stopped=%s', pendingSegments, stopRequested);
      drainQueue();
    });
}

async function stop() {
  if (state !== C.RECORDING) return;
  stopRequested = true;
  setState(C.TRANSCRIBING, true);
  toast('⏳ Transcribiendo...');

  const currentCapture = capture;
  capture = null;
  const currentSegmenter = segmenter;

  try {
    if (currentCapture) {
      await currentCapture.stop();
    }
  } catch (err) {
    log('Stop error:', err && err.message ? err.message : String(err));
  }

  if (currentSegmenter) {
    enqueueSegments(currentSegmenter.flush());
  }
  segmenter = null;

  if (pendingSegments === 0 && queue.length === 0 && !sending) {
    finalizeResult();
  }
}

function finalizeResult() {
  if (accumulatedText && accumulatedText.length >= 2) {
    stopRevealTimer();
    visibleText = accumulatedText;
    setAsrVisibleText(accumulatedText);
    setInput('🎤 ' + accumulatedText);
    toast('✅');
  } else {
    toast('ℹ️ No se grabó bien');
  }
  setState(C.IDLE);
  pendingSegments = 0;
  queue = [];
  sending = false;
  stopRequested = false;
  stopRevealTimer();
  lastSuccessAtMs = 0;
  if (transport) {
    transport.close();
  }
  log('Finalized: %d chars', accumulatedText.length);
}

async function cleanup() {
  const currentCapture = capture;
  capture = null;
  const currentSegmenter = segmenter;
  segmenter = null;
  const currentTransport = transport;
  transport = null;
  queue = [];
  sending = false;
  pendingSegments = 0;
  stopRequested = false;
  accumulatedText = '';
  visibleText = '';
  setAsrVisibleText('');
  stopRevealTimer();
  lastSuccessAtMs = 0;
  if (currentCapture) {
    try { await currentCapture.stop(); } catch (e) {}
  }
  if (currentSegmenter) {
    currentSegmenter.flush();
  }
  if (currentTransport) {
    await currentTransport.close();
  }
  setState(C.IDLE);
}

function applySegmentMode(mode) {
  if (!segmenter) return;
  segmentMode = mode;
  if (mode === 'bootstrap') {
    Object.assign(segmenter.options, BOOTSTRAP_SEGMENT_OPTIONS);
  } else {
    Object.assign(segmenter.options, SEGMENT_OPTIONS);
  }
}

function revealTranscript(targetText) {
  const cleanTarget = (targetText || '').trim();
  const current = (visibleText || '').trim();
  if (!cleanTarget) {
    stopRevealTimer();
    visibleText = '';
    setAsrVisibleText('');
    setInput('🎤 ');
    return;
  }

  const currentTokens = splitTokens(current);
  const targetTokens = splitTokens(cleanTarget);
  let shared = 0;
  while (shared < currentTokens.length && shared < targetTokens.length && currentTokens[shared] === targetTokens[shared]) {
    shared += 1;
  }

  const prefix = targetTokens.slice(0, shared).join(' ');
  const queueTokens = targetTokens.slice(shared);
  stopRevealTimer();
  visibleText = prefix;
  setAsrVisibleText(prefix);
  setInput(prefix ? '🎤 ' + prefix : '🎤 ');
  if (queueTokens.length === 0) {
    visibleText = cleanTarget;
    setAsrVisibleText(cleanTarget);
    setInput('🎤 ' + cleanTarget);
    return;
  }

  let idx = 0;
  const tick = function () {
    const nextToken = queueTokens[idx];
    idx += 1;
    visibleText = (visibleText ? visibleText + ' ' : '') + nextToken;
    setAsrVisibleText(visibleText);
    setInput('🎤 ' + visibleText);
    if (idx >= queueTokens.length) {
      stopRevealTimer();
      visibleText = cleanTarget;
      setAsrVisibleText(cleanTarget);
      setInput('🎤 ' + cleanTarget);
      return;
    }
    const delay = idx < 3 ? 28 : 65;
    revealTimer = window.setTimeout(tick, delay);
  };
  revealTimer = window.setTimeout(tick, 12);
}

function stopRevealTimer() {
  if (revealTimer) {
    clearTimeout(revealTimer);
    revealTimer = null;
  }
}

function toast(msg) {
  const t = document.createElement('div');
  t.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:8px 16px;border-radius:4px;z-index:9999;font-size:14px;';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(function () { t.remove(); }, 3000);
}

log('ASR ready — VAD + AudioWorklet');
