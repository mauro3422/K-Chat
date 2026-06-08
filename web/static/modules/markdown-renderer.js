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
    console.log('[KairosMarkdown] renderAll: found', containers.length, 'containers');
    
    // Configurar DOMPurify para permitir iframes de widgets
    var purifyConfig = {
      ADD_TAGS: ['iframe'],
      ADD_ATTR: ['allow', 'allowfullscreen', 'frameborder', 'scrolling', 'srcdoc', 'sandbox']
    };
    
    containers.forEach(function(el) {
      if (el.dataset.rendered) {
        console.log('[KairosMarkdown] Skipping already rendered container');
        return;
      }
      
      var raw = el.textContent;
      console.log('[KairosMarkdown] Processing container, raw length:', raw.length);
      
      if (raw.trim()) {
        // Decodificar HTML escapado del servidor si es necesario
        var decoded = decodeHtml(raw);
        console.log('[KairosMarkdown] Decoded length:', decoded.length);
        console.log('[KairosMarkdown] Contains html-widget:', decoded.indexOf('html-widget') >= 0);
        
        var parsed = parse(decoded);
        var sanitized = DOMPurify.sanitize(parsed, purifyConfig);
        el.innerHTML = sanitized;
        
        console.log('[KairosMarkdown] After sanitize, iframes:', el.querySelectorAll('iframe').length);
        console.log('[KairosMarkdown] After sanitize, widget containers:', el.querySelectorAll('.interactive-widget-container').length);
        
        // Forzar inicialización inmediata (no usar lazy loading al cargar sesión existente)
        KairosWidgets.initAll(el, true);
        
        console.log('[KairosMarkdown] Rendered and initialized widgets');
      }
      el.dataset.rendered = '1';
    });
  }

  return {
    parse: parse,
    renderAll: renderAll
  };
})();
