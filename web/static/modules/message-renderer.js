function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function _fileIcon(ext) {
  var icons = {
    pdf: "\uD83D\uDCC4", png: "\uD83D\uDDBC\uFE0F", jpg: "\uD83D\uDDBC\uFE0F",
    jpeg: "\uD83D\uDDBC\uFE0F", gif: "\uD83D\uDDBC\uFE0F", webp: "\uD83D\uDDBC\uFE0F",
    mp3: "\uD83C\uDFB5", wav: "\uD83C\uDFB5", ogg: "\uD83C\uDFB5",
    doc: "\uD83D\uDCDD", docx: "\uD83D\uDCDD",
    xls: "\uD83D\uDCCA", xlsx: "\uD83D\uDCCA",
    zip: "\uD83D\uDCE6", rar: "\uD83D\uDCE6", tar: "\uD83D\uDCE6", gz: "\uD83D\uDCE6",
    py: "\uD83D\uDCBB", js: "\uD83D\uDCBB", ts: "\uD83D\uDCBB",
    cpp: "\uD83D\uDCBB", c: "\uD83D\uDCBB", h: "\uD83D\uDCBB",
  };
  return icons[ext] || "\uD83D\uDCCE";
}

function _isImageFile(filename) {
  var ext = filename.split('.').pop().toLowerCase();
  return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tiff', 'tif'].indexOf(ext) !== -1;
}

function _renderFileCard(originalName, savedName) {
  var ext = originalName.split('.').pop().toLowerCase();
  var icon = _fileIcon(ext);
  var displayName = originalName.length > 30 ? originalName.substring(0, 27) + '...' : originalName;

  // Si es imagen y tenemos el saved_name, mostrar inline
  if (_isImageFile(originalName) && savedName) {
    var src = '/chat/' + _currentSessionId + '/attachment/' + savedName;
    return '<div class="file-attach-card file-attach-image">' +
      '<img src="' + src + '" alt="' + escapeHtml(originalName) + '" class="file-attach-preview" loading="lazy" />' +
      '<span class="file-attach-name">' + escapeHtml(displayName) + '</span>' +
      '</div>';
  }

  return '<div class="file-attach-card">' +
    '<span class="file-attach-icon">' + icon + '</span>' +
    '<span class="file-attach-name">' + escapeHtml(displayName) + '</span>' +
    '</div>';
}

var _currentSessionId = '';
export function setCurrentSessionId(sid) { _currentSessionId = sid; }

function _renderAttachments(content) {
  if (!content) return content;
  return content.replace(/\[Archivo:\s*([^|\]]+?)(?:\|([^\]]+))?\]/g, function(match, filename, savedName) {
    return _renderFileCard(filename.trim(), savedName ? savedName.trim() : '');
  });
}

export function renderMessage(msg) {
  const role = msg.role;
  const content = msg.content || "";
  const reasoning = msg.reasoning || "";
  const ts = msg.ts;
  const phases = msg.phases;
  const matched_tools = msg.matched_tools || [];

  const label = role === "user" ? "Tu" : "Kairos";
  const parts = [];

  parts.push('<div class="msg ' + role + '" data-ts="' + (ts || '') + '">');
  parts.push('<div class="msg-label">' + label + '</div>');

  if (role === "assistant" && phases && phases.length > 0) {
    const toolsByTurn = {};
    matched_tools.forEach(t => {
      const turn = t.turn || 0;
      if (!toolsByTurn[turn]) {
        toolsByTurn[turn] = [];
      }
      toolsByTurn[turn].push({ name: t.tool_name, status: t.status });
    });

    const hasAnyPhaseContent = phases.some(p => p.content);

    phases.forEach((phase, idx) => {
      const rText = phase.reasoning || "";
      if (rText) {
        parts.push(
          '<details class="reasoning" open>',
          '<summary>Razonamiento</summary>',
          '<div class="rt">' + escapeHtml(rText) + '</div>',
          '</details>'
        );
      }
      if (hasAnyPhaseContent) {
        const pContent = phase.content || "";
        if (pContent) {
          var rendered = _renderAttachments(escapeHtml(pContent));
          parts.push('<div class="msg-body md-content">' + rendered + '</div>');
        }
      }

      const turnTools = toolsByTurn[idx + 1] || [];
      if (turnTools.length > 0) {
        parts.push('<div class="tool-calls">');
        turnTools.forEach(t => {
          const icon = t.status === "ok" ? "&#10003;" : "&#10007;";
          parts.push('<span class="tc-item ' + t.status + '">' + icon + ' ' + escapeHtml(t.name) + '</span>');
        });
        parts.push('</div>');
      }
    });

    if (!hasAnyPhaseContent) {
      var rendered = _renderAttachments(escapeHtml(content));
      parts.push('<div class="msg-body md-content">' + rendered + '</div>');
    }
  } else {
    if (reasoning) {
      parts.push(
        '<details class="reasoning" open>',
        '<summary>Razonamiento</summary>',
        '<div class="rt">' + escapeHtml(reasoning) + '</div>',
        '</details>'
      );
    }

    const bodyCls = role === "assistant" ? "msg-body md-content" : "msg-body";
    var renderedContent = role === "user" ? _renderAttachments(escapeHtml(content)) : _renderAttachments(content);
    parts.push('<div class="' + bodyCls + '">' + renderedContent + '</div>');

    if (role === "assistant" && matched_tools.length > 0) {
      parts.push('<div class="tool-calls">');
      matched_tools.forEach(t => {
        const icon = t.status === "ok" ? "&#10003;" : "&#10007;";
        parts.push('<span class="tc-item ' + t.status + '">' + icon + ' ' + escapeHtml(t.tool_name) + '</span>');
      });
      parts.push('</div>');
    }
  }

  const tsStr = ts ? String(ts).slice(0, 16) : "";
  parts.push('<div class="msg-ts">' + tsStr + '</div>');
  parts.push('</div>');

  return parts.join("\n");
}

export function renderMessageList(messages, widget_states) {
  const parts = [];
  
  if (!messages || messages.length === 0) {
    parts.push(`<div class="empty-state">Send a message to start</div>`);
  } else {
    messages.forEach(msg => {
      parts.push(renderMessage(msg));
    });
  }

  return parts.join("\n");
}
