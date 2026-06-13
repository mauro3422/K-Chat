import { ApiClient } from './api-client.js';

export function refreshSidebar(containerId) {
  var targetId = containerId || 'session-list';
  return ApiClient.sidebar().then(function(h) {
    var el = document.getElementById(targetId);
    if (el) el.innerHTML = h;
  }).catch(function(err) {
    console.error('Sidebar refresh failed:', err);
  });
}
