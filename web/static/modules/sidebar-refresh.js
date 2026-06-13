import { ApiClient } from './api-client.js';

function setSidebarHtml(el, html) {
  if (typeof document.createElement !== 'function') {
    el.innerHTML = html;
    return;
  }

  var template = document.createElement('template');
  if (!template || !('innerHTML' in template)) {
    el.innerHTML = html;
    return;
  }

  template.innerHTML = html;
  if (typeof el.replaceChildren === 'function' && template.content) {
    el.replaceChildren(template.content.cloneNode(true));
    return;
  }

  el.innerHTML = html;
}

export function refreshSidebar(containerId) {
  var targetId = containerId || 'session-list';
  return ApiClient.sidebar().then(function(h) {
    var el = document.getElementById(targetId);
    if (el) setSidebarHtml(el, h);
  }).catch(function(err) {
    console.error('Sidebar refresh failed:', err);
  });
}
