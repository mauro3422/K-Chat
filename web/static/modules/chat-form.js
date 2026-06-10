var lastUserMessageText = '';
var currentController = null;

function retryLastMessage() {
  var lastAsstMsg = document.querySelector('.msg.assistant:last-child');
  if (lastAsstMsg && lastAsstMsg.querySelector('.error-card')) {
    lastAsstMsg.remove();
  }

  var lastUserText = '';
  var userMsgs = document.querySelectorAll('.msg.user');
  if (userMsgs.length > 0) {
    var lastUserBody = userMsgs[userMsgs.length - 1].querySelector('.msg-body');
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

    lastUserMessageText = text;

    var oldUrl = window.location.pathname;
    if (oldUrl === '/') { window.history.replaceState({sid:sessionId}, '', '/sessions/' + sessionId); }

    input.disabled = true;
    document.getElementById('spinner').textContent = '...';

    document.getElementById('messages').insertAdjacentHTML('beforeend',
      '<div class="msg user"><div class="msg-label">Tu</div><div class="msg-body">' + KairosUtils.escHtml(text) + '</div></div>');
    var asstDiv = document.createElement('div');
    asstDiv.className = 'msg assistant';
    asstDiv.innerHTML = '<div class="msg-label">Kairos</div><div class="msg-body md-content">Pensando...</div>';
    document.getElementById('messages').appendChild(asstDiv);
    KairosUtils.scrollToBottom();

    StreamOrchestrator.startStream({
      text: text,
      form: form,
      input: input,
      asstDiv: asstDiv,
      lastUserMessageText: lastUserMessageText,
      controller: currentController,
      sessionId: sessionId,
      defaultModel: defaultModel
    });
  });
}

function resetForm() {
  lastUserMessageText = '';
  RetryHandler.resetRetryCount();
}

export const KairosForm = {
  init: init,
  retry: retryLastMessage,
  reset: resetForm
};
