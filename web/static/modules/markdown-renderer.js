/* eslint-disable no-redeclare, no-unused-vars */

import C from './dom-contracts.js';
import { KairosWidgets, initAll } from './widgets/index.js';

function decodeHtml(html) {
  // Solo decodificar si contiene entidades HTML escapadas
  if (html.indexOf('&lt;') >= 0 || html.indexOf('&gt;') >= 0 || html.indexOf('&quot;') >= 0) {
    if (typeof DOMParser === 'function') {
      var parsed = new DOMParser().parseFromString('<textarea>' + html + '</textarea>', 'text/html');
      var textarea = parsed.querySelector('textarea');
      if (textarea) {
        return textarea.value;
      }
    }
    return html
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'");
  }
  return html;
}

function parse(text) {
  if (typeof marked === 'undefined') return text;

  var cleanText = KairosWidgets.extract(text);

  cleanText = cleanText.replace(/^([ \t]*\|[ \t]*[:\-\+\| \t]+)$/gm, function(match) {
    return match.replace(/\+/g, '-');
  });
  cleanText = cleanText.replace(/\[\^([^\]]+)\](?!\:)/g, '<sup><a href="#fn-$1" id="fnref-$1" class="fn-ref">$1</a></sup>');
  cleanText = cleanText.replace(/^\[\^([^\]]+)\]:\s*(.*)$/gm, '<div class="footnote-def" id="fn-$1"><a href="#fnref-$1" class="fn-back">↩</a> <strong>$1:</strong> $2</div>');
  return marked.parse(cleanText);
}

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

function setRenderedHtml(el, sanitized) {
  var fragment = htmlToFragment(sanitized);
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

function renderAll() {
  if (typeof marked === 'undefined') return;
  
  var containers = document.querySelectorAll('.' + C.MD_CONTENT);
  
  // Configurar DOMPurify para permitir iframes de widgets y atributos de versión
  var purifyConfig = {
    ADD_TAGS: ['iframe'],
    ADD_ATTR: ['allow', 'allowfullscreen', 'frameborder', 'scrolling', 'srcdoc', 'sandbox', 'data-widget-id', 'data-widget-key']
  };
  if (typeof DOMPurify !== 'undefined') {
    DOMPurify.setConfig(purifyConfig);
  }
  
  containers.forEach(function(el) {
    if (el.dataset.rendered) {
      return;
    }
    
    var raw = el.textContent;
    
    if (raw.trim()) {
      var decoded = decodeHtml(raw);
      
      var parsed = parse(decoded);
      var sanitized = (typeof DOMPurify !== 'undefined') ? DOMPurify.sanitize(parsed, purifyConfig) : parsed;
      setRenderedHtml(el, sanitized);
      
      // Forzar inicialización inmediata (no usar lazy loading al cargar sesión existente)
      initAll(el, true);
    }
    el.dataset.rendered = '1';
  });
}

export const KairosMarkdown = { parse, renderAll };
