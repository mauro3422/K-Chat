import { StreamOrchestrator } from './stream-orchestrator.js';
import { createRetryController } from './retry-handler.js';
import { KairosUtils } from './utils.js';
import C from './dom-contracts.js';
import { SessionContext } from './session-context.js';

var lastUserMessageText = '';
var currentController = null;
var currentRetryController = createRetryController();
var retryClickBound = false;

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

function init() {
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

    var oldUrl = window.location.pathname;
    if (oldUrl === '/') { window.history.replaceState({sid:SessionContext.getSessionId()}, '', '/sessions/' + SessionContext.getSessionId()); }

    input.disabled = true;
    document.getElementById('spinner').textContent = '...';

    document.getElementById('messages').insertAdjacentHTML('beforeend',
      '<div class="msg user"><div class="msg-label">Tu</div><div class="' + C.MSG_BODY + '">' + KairosUtils.escHtml(text) + '</div></div>');
    var asstDiv = document.createElement('div');
    asstDiv.className = 'msg assistant';
    asstDiv.innerHTML = '<div class="msg-label">Kairos</div><div class="' + C.MSG_BODY_MD() + '">Pensando...</div>';
    document.getElementById('messages').appendChild(asstDiv);
    KairosUtils.scrollToBottom();

    StreamOrchestrator.startStream({
      text: text,
      form: form,
      input: input,
      asstDiv: asstDiv,
      lastUserMessageText: lastUserMessageText,
      controller: currentController,
      retryController: currentRetryController,
      sessionId: SessionContext.getSessionId(),
      defaultModel: defaultModel
    });
  });
}

function resetForm() {
  lastUserMessageText = '';
  currentRetryController.resetRetryCount();
}

export const KairosForm = {
  init: init,
  retry: retryLastMessage,
  reset: resetForm
};
