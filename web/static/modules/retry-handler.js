import { KairosUtils } from './utils.js';
import C from './dom-contracts.js';

function delay(ms) {
  return new Promise(function(resolve) { setTimeout(resolve, ms); });
}

export class RetryController {
  constructor() {
    this.count = 0;
    this.maxRetries = 3;
    this.streamTimeout = null;
  }

  showRetryNotice(attempt, reason) {
    KairosUtils.showToast('Reintentando... (' + attempt + '/' + this.maxRetries + ') - ' + reason, 'warning');
    logUI('stream_retry', 'intento ' + attempt + '/' + this.maxRetries + ' - ' + reason);
  }

  scheduleRetry(form, input, asstDiv, lastUserMessageText, reason) {
    this.count++;
    this.showRetryNotice(this.count, reason);
    var bodyDiv = asstDiv.querySelector('.' + C.MSG_BODY);
    if (bodyDiv) bodyDiv.innerHTML = '';
    var toRemove = asstDiv.querySelectorAll('.' + C.REASONING + ', .' + C.TOOL_CALLS);
    for (var r = 0; r < toRemove.length; r++) {
      toRemove[r].remove();
    }
    input.value = lastUserMessageText;
    return delay(2000 * this.count).then(function doScheduledSubmit() {
      form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    });
  }

  shouldRetry(hasContent) {
    return this.count < this.maxRetries && !hasContent;
  }

  incrementRetry() {
    this.count++;
  }

  resetRetryCount() {
    this.count = 0;
  }

  getRetryCount() {
    return this.count;
  }

  getMaxRetries() {
    return this.maxRetries;
  }

  getStreamTimeout() {
    return this.streamTimeout || 120000;
  }
}

export function createRetryController() {
  return new RetryController();
}

export const RetryHandler = createRetryController();
