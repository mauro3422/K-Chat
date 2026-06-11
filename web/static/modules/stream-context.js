import { ReasoningState } from './reasoning-state.js';

export class StreamContext {
  #bodyDivs;
  #contentTexts;
  #reasoningEls;
  #reasoningText;
  #reasoningState;
  #toolPhase;
  #toolTurnSinceLastContent;
  #widgetCache;
  #widgetMap;
  #asstDiv;
  #firstToken;

  constructor(asstDiv) {
    if (!asstDiv) throw new Error('asstDiv is required');
    this.#asstDiv = asstDiv;
    this.#bodyDivs = [asstDiv.querySelector('.msg-body')];
    this.#contentTexts = [''];
    this.#reasoningEls = [];
    this.#reasoningText = '';
    this.#reasoningState = new ReasoningState();
    this.#toolPhase = 0;
    this.#toolTurnSinceLastContent = false;
    this.#widgetCache = {};
    this.#widgetMap = {};
    this.#firstToken = true;
  }

  getBodyDivs() {
    return this.#bodyDivs;
  }

  getContentText(phaseIdx) {
    return this.#contentTexts[phaseIdx] || '';
  }

  setContentText(phaseIdx, text) {
    while (this.#contentTexts.length <= phaseIdx) {
      this.#contentTexts.push('');
    }
    this.#contentTexts[phaseIdx] = text;
  }

  appendContentText(phaseIdx, token) {
    while (this.#contentTexts.length <= phaseIdx) {
      this.#contentTexts.push('');
    }
    this.#contentTexts[phaseIdx] += token;
  }

  getReasoningEls() {
    return this.#reasoningEls;
  }

  getReasoningText() {
    return this.#reasoningText;
  }

  setReasoningText(text) {
    this.#reasoningText = text;
  }

  appendReasoningText(token) {
    this.#reasoningText += token;
  }

  getReasoningState() {
    return this.#reasoningState;
  }

  isReasoningActive() {
    return this.#reasoningState.isActive;
  }

  enterReasoningPhase() {
    return this.#reasoningState.enter();
  }

  exitReasoningPhase() {
    this.#reasoningState.exit();
  }

  enterToolPhase() {
    if (this.#toolTurnSinceLastContent) {
      this.#toolTurnSinceLastContent = false;
      this.#toolPhase = (this.#toolPhase || 0) + 1;
    }
    return this.#toolPhase;
  }

  getToolPhase() {
    return this.#toolPhase;
  }

  markToolTurn() {
    this.#toolTurnSinceLastContent = true;
  }

  getToolTurnSinceLastContent() {
    return this.#toolTurnSinceLastContent;
  }

  getAsstDiv() {
    return this.#asstDiv;
  }

  getWidgetCache(phaseIdx) {
    var key = String(phaseIdx);
    if (!this.#widgetCache[key]) {
      this.#widgetCache[key] = {};
    }
    return this.#widgetCache[key];
  }

  getWidgetMap(phaseIdx) {
    var key = String(phaseIdx);
    if (!this.#widgetMap[key]) {
      this.#widgetMap[key] = {};
    }
    return this.#widgetMap[key];
  }

  isFirstToken() {
    return this.#firstToken;
  }

  clearFirstToken() {
    this.#firstToken = false;
  }

  ensureBodyDiv(phaseIdx, className) {
    while (this.#bodyDivs.length <= phaseIdx) {
      var newBody = document.createElement('div');
      newBody.className = className || 'msg-body md-content';
      this.#asstDiv.appendChild(newBody);
      this.#bodyDivs.push(newBody);
      this.#contentTexts.push('');
    }
    return this.#bodyDivs[phaseIdx];
  }

  addReasoningEl(el) {
    this.#reasoningEls.push(el);
  }

  getLastReasoningEl() {
    if (this.#reasoningEls.length === 0) return null;
    return this.#reasoningEls[this.#reasoningEls.length - 1];
  }

  getPhaseIndex() {
    return Math.max(0, this.#reasoningEls.length - 1) + (this.#toolPhase || 0);
  }

  reset() {
    this.#bodyDivs = [this.#asstDiv.querySelector('.msg-body')];
    this.#contentTexts = [''];
    this.#reasoningEls = [];
    this.#reasoningText = '';
    this.#reasoningState = new ReasoningState();
    this.#toolPhase = 0;
    this.#toolTurnSinceLastContent = false;
    this.#widgetCache = {};
    this.#widgetMap = {};
    this.#firstToken = true;
  }
}

window.StreamContext = StreamContext;
