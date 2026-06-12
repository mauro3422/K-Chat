/* eslint-disable no-redeclare, no-unused-vars */

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function scrollToBottom() {
  var el = document.getElementById('messages');
  if (el) el.scrollTop = el.scrollHeight;
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
  input.focus();
  scrollToBottom();
}

export const KairosUtils = { escHtml, scrollToBottom, initGlobalErrorHandlers, showToast, finalizeStream };
