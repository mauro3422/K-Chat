import { StreamOrchestrator } from './stream-orchestrator.js';
import { createRetryController } from './retry-handler.js';
import { Utils } from './utils.js';
import C from './dom-contracts.js';
import { SessionContext } from './session-context.js';

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

function buildMessageNode(roleClass, label, bodyClass, bodyText) {
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

    var submitBtn = document.getElementById('chat-submit-btn');
    if (submitBtn && submitBtn.classList.contains('btn-stop')) {
      if (currentController) currentController.abort();
      return;
    }

    var input = document.getElementById('msg-input');
    if (!input) input = form.querySelector('input[name="message"]');
    if (!input) return;
    var text = input.value.trim();
    if (!text) return;

    if (currentController) currentController.abort();
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

    var messages = document.getElementById('messages');
    if (messages) {
      messages.appendChild(buildMessageNode('user', 'Tu', C.MSG_BODY, text));
    }
    var asstDiv = buildMessageNode('assistant', 'Kairos', C.MSG_BODY_MD(), 'Pensando...');
    if (messages) {
      messages.appendChild(asstDiv);
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
      defaultModel: getDefaultModel()
    });
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
