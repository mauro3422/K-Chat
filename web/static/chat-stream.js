window.widgetStates = window.widgetStates || {};

window.retryLastMessage = function() { KairosForm.retry(); };
window.escHtml = function(s) { return KairosUtils.escHtml(s); };

KairosWidgets.startMessageHandler();
KairosForm.init();

document.addEventListener('DOMContentLoaded', KairosMarkdown.renderAll);

document.addEventListener('DOMContentLoaded', function() {
  if (window.location.pathname.startsWith('/sessions/')) {
    fetch('/sessions/' + sessionId + '/messages')
      .then(function(r) { return r.text(); })
      .then(function(h) {
        var main = document.getElementById('main');
        if (main) {
          main.innerHTML = h;
          KairosMarkdown.renderAll();
        }
      });
  }
});
