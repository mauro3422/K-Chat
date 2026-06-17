import C from './dom-contracts.js';
import { logUI } from '../../src_ts/core/infra/LogUI';
import { StreamDispatcher } from './stream-dispatcher.js';

type ReasoningStateLike = {
  enter(): boolean;
};

type ReasoningContextLike = {
  getReasoningState(): ReasoningStateLike;
  getReasoningEls(): HTMLElement[];
  getAsstDiv(): HTMLElement;
  getBodyDivs(): HTMLElement[];
  getToolTurnSinceLastContent(): boolean;
  consumeToolTurn(): void;
  appendReasoningText(token: string): void;
};

type ReasoningEventContext = {
  reasoningEls: HTMLElement[];
  asstDiv: HTMLElement;
  bodyDivs: HTMLElement[];
  reasoningState: ReasoningStateLike;
  reasoningText: string;
  context?: ReasoningContextLike;
};

export function registerReasoningHandler(): void {
  StreamDispatcher.on('reasoning', function(token: string, ctx: ReasoningContextLike | ReasoningEventContext) {
    try {
      let state: ReasoningEventContext = ctx as ReasoningEventContext;
      if (ctx && typeof (ctx as ReasoningContextLike).getReasoningState === 'function') {
        const typedCtx = ctx as ReasoningContextLike;
        state = {
          reasoningEls: typedCtx.getReasoningEls(),
          asstDiv: typedCtx.getAsstDiv(),
          bodyDivs: typedCtx.getBodyDivs(),
          reasoningState: typedCtx.getReasoningState(),
          reasoningText: '',
          context: typedCtx,
        };
      }

      state.reasoningText += token;
      if (state.context) {
        state.context.appendReasoningText(token);
      }
      const isNewPhase = state.reasoningState.enter();
      if (isNewPhase) {
        if (state.context && state.context.getToolTurnSinceLastContent()) {
          state.context.consumeToolTurn();
        }
        const newDet = document.createElement('details');
        newDet.className = C.REASONING;
        newDet.open = true;
        const summary = document.createElement('summary');
        summary.textContent = 'Razonando...';
        const rt = document.createElement('div');
        rt.className = C.RT;
        newDet.appendChild(summary);
        newDet.appendChild(rt);

        if (state.reasoningEls.length > 0) {
          const prev = state.reasoningEls[state.reasoningEls.length - 1];
          prev.querySelector('summary')!.textContent = 'Razonamiento';
          prev.open = false;
          state.asstDiv.appendChild(newDet);
        } else if (state.bodyDivs[0]) {
          state.bodyDivs[0].insertAdjacentElement('beforebegin', newDet);
        } else {
          state.asstDiv.appendChild(newDet);
        }
        state.reasoningEls.push(newDet);
        logUI('reasoning_phase', state.reasoningEls.length);
      }
      const last = state.reasoningEls[state.reasoningEls.length - 1];
      const rt = last ? last.querySelector('.' + C.RT) : null;
      if (rt) rt.textContent += token;
    } catch (e) {
      console.error('Reasoning handler error:', e);
    }
  });
}

registerReasoningHandler();
