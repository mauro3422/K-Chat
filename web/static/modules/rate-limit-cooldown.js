/**
 * Rate Limit Cooldown — prevents spamming when the LLM provider is rate-limited.
 *
 * When a 429 / FreeUsageLimitError is detected:
 *   1. Disables the chat input
 *   2. Shows a countdown timer on the send button
 *   3. Re-enables input when cooldown expires
 *
 * Default cooldown: 60 seconds (free tier typical reset window).
 */

var _cooldownActive = false;
var _cooldownEnd = 0;
var _timerId = null;
var _onTick = null;
var _onExpire = null;

var DEFAULT_COOLDOWN_MS = 60000;

function isActive() {
  return _cooldownActive && Date.now() < _cooldownEnd;
}

function getRemainingMs() {
  if (!isActive()) return 0;
  return _cooldownEnd - Date.now();
}

function getRemainingSec() {
  return Math.ceil(getRemainingMs() / 1000);
}

function _disableInput() {
  var input = document.getElementById('msg-input');
  if (input) {
    input.dataset.originalPlaceholder = input.placeholder;
    input.disabled = true;
    input.placeholder = '⏳ Rate limit activo — esperá al countdown...';
  }
  var btn = document.getElementById('chat-submit-btn');
  if (btn) {
    btn.classList.add('btn-rate-limited');
    btn.title = 'Rate limit activo';
  }
}

function _enableInput() {
  var input = document.getElementById('msg-input');
  if (input) {
    input.disabled = false;
    input.placeholder = input.dataset.originalPlaceholder || 'Escribe un mensaje...';
    delete input.dataset.originalPlaceholder;
  }
  var btn = document.getElementById('chat-submit-btn');
  if (btn) {
    btn.classList.remove('btn-rate-limited');
    btn.title = '';
  }
}

function _updateButton() {
  var btn = document.getElementById('chat-submit-btn');
  if (!btn) return;
  var sec = getRemainingSec();
  if (sec <= 0) {
    btn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>';
    return;
  }
  btn.innerHTML = '<span class="cooldown-countdown">' + sec + 's</span>';
}

function _tick() {
  if (!isActive()) {
    _expire();
    return;
  }
  _updateButton();
  if (_onTick) _onTick(getRemainingSec());
}

function _expire() {
  _cooldownActive = false;
  _cooldownEnd = 0;
  if (_timerId) {
    clearInterval(_timerId);
    _timerId = null;
  }
  _enableInput();
  _updateButton();
  if (_onExpire) _onExpire();
}

/**
 * Start or extend a cooldown period.
 * @param {number} [ms] - Cooldown duration in ms. Default: 60000.
 * @param {object} [opts] - { onTick: fn(sec), onExpire: fn() }
 */
function startCooldown(ms, opts) {
  var duration = ms || DEFAULT_COOLDOWN_MS;
  _cooldownActive = true;
  _cooldownEnd = Date.now() + duration;
  if (opts) {
    _onTick = opts.onTick || null;
    _onExpire = opts.onExpire || null;
  }

  _disableInput();
  _updateButton();

  if (_timerId) clearInterval(_timerId);
  _timerId = setInterval(_tick, 1000);
}

function cancelCooldown() {
  _expire();
}

/**
 * Can the form be submitted right now?
 * Returns true if allowed, false if cooldown is active.
 */
function canSubmit() {
  if (!isActive()) return true;
  return false;
}

export const RateLimitCooldown = {
  isActive: isActive,
  getRemainingMs: getRemainingMs,
  getRemainingSec: getRemainingSec,
  startCooldown: startCooldown,
  cancelCooldown: cancelCooldown,
  canSubmit: canSubmit
};
