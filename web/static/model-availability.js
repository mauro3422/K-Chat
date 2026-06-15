// Model availability checker — live status dots
(async function() {
  try {
    var res = await fetch('/models/availability');
    if (!res.ok) return;
    var data = await res.json();
    if (!data.models) return;
    var select = document.getElementById('model-select');
    if (!select) return;
    var limitedCount = data.limited_count || 0;

    for (var i = 0; i < select.options.length; i++) {
      var opt = select.options[i];
      var info = data.models[opt.value];
      if (!info) continue;

      // Remove old status prefix
      var clean = opt.textContent.replace(/^[🔴🟢⚪]?\s*/, '');
      // Remove cooldown badge if any
      clean = clean.replace(/\s+🔒\s*\d+s$/, '');

      if (info.status === 'rate_limited') {
        var cd = info.cooldown_remaining || 0;
        opt.textContent = '🔴 ' + clean + '  🔒 ' + Math.round(cd) + 's';
        opt.style.opacity = '0.5';
      } else if (info.status === 'available') {
        opt.textContent = '🟢 ' + clean;
        opt.style.opacity = '1';
      } else if (info.status === 'unavailable') {
        opt.textContent = '❌ ' + clean + ' (expired)';
        opt.style.opacity = '0.35';
        opt.disabled = true;
      } else {
        opt.textContent = '⚪ ' + clean;
        opt.style.opacity = '0.85';
      }
    }

    if (limitedCount > 0) {
      var mic = document.getElementById('asr-mic-btn');
      if (mic && !document.getElementById('rl-badge')) {
        var badge = document.createElement('span');
        var badge = document.createElement('span');
        badge.id = 'rl-badge';
        badge.textContent = '⚠️ ' + limitedCount;
        badge.title = limitedCount + ' modelo(s) rate-limited';
        badge.style.cssText = 'position:absolute;top:-6px;right:-6px;font-size:9px;background:var(--accent-red);color:#fff;border-radius:50%;width:16px;height:16px;display:flex;align-items:center;justify-content:center;cursor:pointer;line-height:1;';
        badge.onclick = function() {
          if (d) d.style.display = d.style.display === 'none' ? 'flex' : 'none';
        };
        select.parentNode.appendChild(badge);
      }
    }

    // Show Go quota warning if exhausted
    var quotaWarning = document.getElementById('go-quota-warning');
    if (data.go_quota_exhausted) {
      if (!quotaWarning) {
        quotaWarning = document.createElement('div');
        quotaWarning.id = 'go-quota-warning';
        quotaWarning.textContent = '⚠️ Go plan quota agotada — los modelos Go no funcionarán hasta que recargues';
        quotaWarning.style.cssText = 'background:var(--accent-red);color:#fff;padding:6px 12px;font-size:13px;text-align:center;border-radius:6px;margin-bottom:8px;';
        var header = document.querySelector('.chat-header') || select.parentNode;
        header.parentNode.insertBefore(quotaWarning, header);
      }
    } else if (quotaWarning) {
      quotaWarning.remove();
    }

    // Refresh every 30s
    setTimeout(arguments.callee, 30000);
  } catch(e) { /* silently retry */ setTimeout(arguments.callee, 60000); }
})();
