/* eslint-disable no-redeclare, no-unused-vars */

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function isNearBottom(el, threshold) {
  if (!el) return true;
  threshold = threshold || 80;
  return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
}

function scrollToBottom() {
  var el = document.getElementById('messages');
  if (el) el.scrollTop = el.scrollHeight;
}

function scrollToBottomIfNear(threshold) {
  var el = document.getElementById('messages');
  if (el && isNearBottom(el, threshold)) {
    el.scrollTop = el.scrollHeight;
  }
}

function initGlobalErrorHandlers() {
  window.addEventListener('unhandledrejection', function(event) {
    console.error('Unhandled promise rejection:', event.reason);
    showToast('Error: ' + (event.reason && event.reason.message || event.reason || 'desconocido'));
  });

  window.addEventListener('error', function(event) {
    console.error('Global error:', event.message, 'at', event.filename + ':' + event.lineno);
  });
}

function showToast(message, type) {
  var existing = document.getElementById('kairos-toast');
  if (existing) existing.remove();

  var colors = {
    warning: { bg: '#f39c12', text: '#fff' },
    error: { bg: '#f85149', text: '#fff' },
    info: { bg: '#58a6ff', text: '#fff' },
    success: { bg: '#3fb950', text: '#fff' }
  };
  var color = colors[type] || colors.info;

  var toast = document.createElement('div');
  toast.id = 'kairos-toast';
  toast.style.cssText = 'position:fixed;bottom:20px;right:20px;background:' + color.bg + ';color:' + color.text + ';padding:12px 20px;border-radius:8px;z-index:9999;font-size:14px;box-shadow:0 4px 12px rgba(0,0,0,0.3);cursor:pointer;';
  toast.textContent = message;
  toast.onclick = function() { toast.remove(); };
  document.body.appendChild(toast);
  setTimeout(function() { if (toast.parentNode) toast.remove(); }, 8000);
}

function finalizeStream(input) {
  input.disabled = false;
  input.value = '';
  var spinner = document.getElementById('spinner');
  if (spinner) spinner.textContent = '';

  var btn = document.getElementById('chat-submit-btn');
  if (btn) {
    btn.className = '';
    btn.title = 'Enviar mensaje';
    btn.innerHTML = '<svg class="send-svg" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>';
  }

  input.focus();
  scrollToBottom();
}

export const Utils = { escHtml, scrollToBottom, scrollToBottomIfNear, isNearBottom, initGlobalErrorHandlers, showToast, finalizeStream };
