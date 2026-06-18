import type { MessageData } from './messages';

export interface IMessageView {
  init(): void;
  appendMessage(msg: MessageData): HTMLElement | null;
  beginStreaming(role: 'user' | 'assistant'): HTMLElement | null;
  endStreaming(): void;
  clearContainer(): void;
}
