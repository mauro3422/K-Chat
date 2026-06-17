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

function applyFavFilter() {
  var cb = document.getElementById('fav-filter-cb');
  var list = document.getElementById('session-list');
  if (!cb || !list) return;
  list.classList.toggle('fav-filter-active', cb.checked);
}

var _favFilterInit = false;

function initFavFilter() {
  if (_favFilterInit) return;
  _favFilterInit = true;
  document.addEventListener('change', function(e) {
    if (e.target.id === 'fav-filter-cb') {
      applyFavFilter();
    }
  });
}

export function refreshSidebar(containerId) {
  initFavFilter();
  var targetId = containerId || 'session-list';
  return ApiClient.sidebar().then(function(h) {
    var el = document.getElementById(targetId);
    if (el) setSidebarHtml(el, h);
    applyFavFilter();
  }).catch(function(err) {
    console.error('Sidebar refresh failed:', err);
  });
}
