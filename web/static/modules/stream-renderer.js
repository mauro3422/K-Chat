import { KairosStream } from './stream-dispatcher.js';

export function initStreamRenderer() {
  if (!KairosStream) {
    console.error('KairosStream not defined');
    return;
  }
}

initStreamRenderer();
