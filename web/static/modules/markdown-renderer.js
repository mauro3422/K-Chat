/* eslint-disable no-redeclare, no-unused-vars */
var KairosMarkdown = (function() {
  function decodeHtml(html) {
    // Solo decodificar si contiene entidades HTML escapadas
    if (html.indexOf('&lt;') >= 0 || html.indexOf('&gt;') >= 0 || html.indexOf('&quot;') >= 0) {
      var txt = document.createElement('textarea');
      txt.innerHTML = html;
      return txt.value;
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

  function renderAll() {
    if (typeof marked === 'undefined') return;
    
    var containers = document.querySelectorAll('.md-content');
    
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
        el.innerHTML = sanitized;
        
        // Forzar inicialización inmediata (no usar lazy loading al cargar sesión existente)
        KairosWidgets.initAll(el, true);
      }
      el.dataset.rendered = '1';
    });
  }

  return {
    parse: parse,
    renderAll: renderAll
  };
})();
