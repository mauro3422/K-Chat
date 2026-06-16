export interface IRendererContext {
  getCurrentPhaseIndex(): number;
  enterToolPhase(): void;
  getToolPhase(): number;
  ensureBodyContainer(phaseIdx: number, className: string): void;
  appendToken(phaseIdx: number, token: string): void;
}

export interface IDomRenderer {
  renderMessage(container: HTMLElement, content: string, isMarkdown: boolean): void;
  renderReasoning(container: HTMLElement, text: string): void;
  renderToolCall(container: HTMLElement, data: unknown): void;
  clearThinking(container: HTMLElement): void;
}
