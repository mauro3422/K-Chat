import { ApiClient } from './api-client.js';

function htmlToFragment(html) {
  if (typeof document.createRange === 'function') {
    var range = document.createRange();
    if (range && typeof range.createContextualFragment === 'function') {
      return range.createContextualFragment(html);
    }
  }

  var fragment = document.createDocumentFragment();
  var holder = document.createElement('div');
  holder.textContent = html;
  fragment.appendChild(holder);
  return fragment;
}

function setSidebarHtml(el, html) {
  var fragment = htmlToFragment(html);
  if (typeof el.replaceChildren === 'function') {
    el.replaceChildren(fragment);
    return;
  }

  if (typeof el.appendChild === 'function') {
    while (el.firstChild) {
      el.removeChild(el.firstChild);
    }
    el.appendChild(fragment);
  }
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
