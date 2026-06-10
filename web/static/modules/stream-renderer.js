(function() {
  if (typeof KairosStream === 'undefined') {
    console.error('KairosStream is not defined. Cannot initialize stream renderer.');
    return;
  }
  // Handlers auto-register via KairosStream.on() in:
  // - reasoning-handler.js
  // - content-handler.js
  // - tool-call-renderer.js
})();
