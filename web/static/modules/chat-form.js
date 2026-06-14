import { StreamOrchestrator } from './stream-orchestrator.js';
import { createRetryController } from './retry-handler.js';
import { Utils } from './utils.js';
import C from './dom-contracts.js';
import { SessionContext } from './session-context.js';
import { FileAttachment } from './file-attachment.js';
import { RateLimitCooldown } from './rate-limit-cooldown.js';

var lastUserMessageText = '';
var currentController = null;
var currentRetryController = createRetryController();
var retryClickBound = false;

function getNav(deps) {
  if (!deps || !deps.nav) {
    throw new Error('ChatForm.init requires nav');
  }
  return deps.nav;
}

function getDefaultModel() {
  try { return localStorage.getItem('selected_model') || 'deepseek-v4-flash-free'; }
  catch(e) { return 'deepseek-v4-flash-free'; }
}

function buildMessageNode(roleClass, label, bodyClass, bodyText, files) {
  var msg = document.createElement('div');
  msg.className = 'msg ' + roleClass;

  var labelDiv = document.createElement('div');
  labelDiv.className = 'msg-label';
  labelDiv.textContent = label;

  var bodyDiv = document.createElement('div');
  bodyDiv.className = bodyClass;
  bodyDiv.textContent = bodyText;

  msg.appendChild(labelDiv);
  msg.appendChild(bodyDiv);

  // Si hay archivos adjuntos, agregar fichas visuales
  if (files && files.length > 0) {
    files.forEach(function(file) {
      var card = document.createElement('div');
      card.className = 'file-attach-card';

      var icon = document.createElement('span');
      icon.className = 'file-attach-icon';
      var ext = file.name.split('.').pop().toLowerCase();
      var icons = {
        pdf: '\uD83D\uDCC4', png: '\uD83D\uDDBC\uFE0F', jpg: '\uD83D\uDDBC\uFE0F',
        jpeg: '\uD83D\uDDBC\uFE0F', gif: '\uD83D\uDDBC\uFE0F', webp: '\uD83D\uDDBC\uFE0F',
        mp3: '\uD83C\uDFB5', wav: '\uD83C\uDFB5', ogg: '\uD83C\uDFB5',
        doc: '\uD83D\uDCDD', docx: '\uD83D\uDCDD',
        zip: '\uD83D\uDCE6', rar: '\uD83D\uDCE6',
        py: '\uD83D\uDCBB', js: '\uD83D\uDCBB', ts: '\uD83D\uDCBB',
        cpp: '\uD83D\uDCBB', c: '\uD83D\uDCBB',
      };
      icon.textContent = icons[ext] || '\uD83D\uDCCE';
      card.appendChild(icon);

      var name = document.createElement('span');
      name.className = 'file-attach-name';
      name.textContent = file.name.length > 30 ? file.name.substring(0, 27) + '...' : file.name;
      card.appendChild(name);

      msg.appendChild(card);
    });
  }

  return msg;
}

function retryLastMessage() {
  var lastAsstMsg = document.querySelector('.msg.assistant:last-child');
  if (lastAsstMsg && lastAsstMsg.querySelector('.' + C.ERROR_CARD)) {
    lastAsstMsg.remove();
  }

  var lastUserText = '';
  var userMsgs = document.querySelectorAll('.msg.user');
  if (userMsgs.length > 0) {
    var lastUserBody = userMsgs[userMsgs.length - 1].querySelector('.' + C.MSG_BODY);
    if (lastUserBody) {
      lastUserText = lastUserBody.innerText || lastUserBody.textContent || '';
    }
  }

  var input = document.getElementById('msg-input');
  if (input) {
    input.disabled = false;
    input.value = lastUserText.trim() || lastUserMessageText;
    var form = document.getElementById('chat-form');
    if (form) {
      form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    }
  }
}

function init(deps) {
  FileAttachment.init();
  if (!retryClickBound) {
    retryClickBound = true;
    document.addEventListener('click', function(event) {
      var target = event.target && event.target.closest ? event.target.closest('.error-retry-btn') : null;
      if (!target) return;
      event.preventDefault();
      retryLastMessage();
    });
  }
  document.addEventListener('submit', function onSubmit(e) {
    var form = e.target;
    if (form.id !== 'chat-form') return;
    e.preventDefault();

    var input = document.getElementById('msg-input');
    var text = input ? input.value.trim() : '';
    if (!text) return;

    var currentFiles = FileAttachment.hasFiles() ? FileAttachment.getFiles() : [];

    var submitBtn = document.getElementById('chat-submit-btn');
    if (submitBtn && submitBtn.classList.contains('btn-stop')) {
      if (currentController) currentController.abort();
      return;
    }
    var messages = document.getElementById('messages');
    if (messages) {
      messages.appendChild(buildMessageNode('user', 'Tu', C.MSG_BODY, text, currentFiles));
    }
    var asstDiv = buildMessageNode('assistant', 'Kairos', C.MSG_BODY_MD(), 'Pensando...');
    if (messages) {
      messages.appendChild(asstDiv);
    }
    currentController = new AbortController();
    if (!currentRetryController || text !== lastUserMessageText) {
      currentRetryController = createRetryController();
    }

    lastUserMessageText = text;

    var nav = getNav(deps);
    var oldUrl = nav.location.pathname;
    if (oldUrl === '/') { nav.history.replaceState({sid:SessionContext.getSessionId()}, '', '/sessions/' + SessionContext.getSessionId()); }

    input.disabled = true;
    document.getElementById('spinner').textContent = '...';

    // Set button to stop state
    if (submitBtn) {
      submitBtn.className = 'btn-stop';
      submitBtn.title = 'Detener generación (Esc)';
      submitBtn.innerHTML = '<svg class="stop-svg" viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"></rect></svg>';
    }

    Utils.scrollToBottom();

    StreamOrchestrator.startStream({
      text: text,
      form: form,
      input: input,
      asstDiv: asstDiv,
      lastUserMessageText: lastUserMessageText,
      controller: currentController,
      retryController: currentRetryController,
      sessionId: SessionContext.getSessionId(),
      defaultModel: getDefaultModel(),
      files: currentFiles
    });

    FileAttachment.clear();
  });

  window.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
      var submitBtn = document.getElementById('chat-submit-btn');
      if (submitBtn && submitBtn.classList.contains('btn-stop')) {
        if (currentController) {
          event.preventDefault();
          currentController.abort();
        }
      }
    }
  });

  // ── Enter para enviar (sin Shift) ────────────────────────────────────
  var input = document.getElementById('msg-input');
  if (input) {
    input.addEventListener('keydown', function(event) {
      if (event.key === 'Enter' && !event.shiftKey && !event.ctrlKey && !event.altKey) {
        event.preventDefault();
        if (input.value.trim()) {
          document.getElementById('chat-form').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
        }
      }
    });
  }
}

function resetForm() {
  lastUserMessageText = '';
  currentRetryController.resetRetryCount();
}

export const ChatForm = {
  init: init,
  retry: retryLastMessage,
  reset: resetForm
};
