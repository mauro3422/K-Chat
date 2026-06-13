import { logUI } from './log-ui.js';

var _loggers = {};
var _logBuffer = [];
var _flushTimer = null;

function factory(name) {
  if (!_loggers[name]) _loggers[name] = new Logger(name);
  return _loggers[name];
}

class Logger {
  constructor(name) {
    this.name = name;
  }

  debug(msg, data) { this._log('D', msg, data); }
  info(msg, data) { this._log('I', msg, data); }
  warn(msg, data) { this._log('W', msg, data); }
  error(msg, data) { this._log('E', msg, data); }

  _log(level, msg, data) {
    var entry = {
      t: new Date().toISOString(),
      l: level,
      m: this.name,
      msg: String(msg).substring(0, 2000),
      d: data || null,
    };
    _logBuffer.push(entry);

    // Mirror to console for active debugging
    if (level === 'E') console.error('[' + this.name + ']', msg, data || '');
    else if (level === 'W') console.warn('[' + this.name + ']', msg, data || '');
    else console.log('[' + this.name + ']', msg, data || '');

    // Also feed into existing debug panel
    try {
      logUI('[' + level + '][' + this.name + ']', String(msg).substring(0, 120));
    } catch (e) {
      // Silently skip UI logging
    }

    this._scheduleFlush();
  }

  _scheduleFlush() {
    if (_flushTimer) return;
    _flushTimer = setTimeout(function() {
      _flushTimer = null;
      _flush();
    }, 2000);
  }
}

function _flush() {
  if (_logBuffer.length === 0) return;
  var batch = _logBuffer.splice(0, Math.min(_logBuffer.length, 100));
  fetch('/api/logs/client', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(batch),
    keepalive: true,
  }).catch(function() {});
}

export var getLogger = factory;
