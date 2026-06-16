import { MessageData } from '../rendering/MessageView';

export interface IMessageView {
  init(): void;
  appendMessage(msg: MessageData): HTMLElement | null;
  beginStreaming(role: 'user' | 'assistant'): HTMLElement | null;
  clearContainer(): void;
}
