import { Window } from 'happy-dom';

const window = new Window({ url: 'http://localhost/' });

globalThis.window = window;
globalThis.document = window.document;
globalThis.self = window;
const originalDispatchEvent = window.dispatchEvent.bind(window);
window._lastEvent = null;
window.dispatchEvent = function(event) {
  window._lastEvent = event;
  return originalDispatchEvent(event);
};
Object.defineProperty(globalThis, 'navigator', {
  value: window.navigator,
  configurable: true,
  writable: true,
});
globalThis.location = window.location;
globalThis.history = window.history;
globalThis.localStorage = window.localStorage;
globalThis.sessionStorage = window.sessionStorage;
globalThis.CustomEvent = window.CustomEvent;
globalThis.Event = window.Event;
globalThis.KeyboardEvent = window.KeyboardEvent;
globalThis.MouseEvent = window.MouseEvent;
globalThis.HTMLElement = window.HTMLElement;
globalThis.HTMLFormElement = window.HTMLFormElement;
globalThis.HTMLTextAreaElement = window.HTMLTextAreaElement;
globalThis.HTMLButtonElement = window.HTMLButtonElement;
globalThis.HTMLDivElement = window.HTMLDivElement;
globalThis.HTMLIFrameElement = window.HTMLIFrameElement;
globalThis.DOMParser = window.DOMParser;
globalThis.Node = window.Node;
globalThis.Element = window.Element;
globalThis.Text = window.Text;
globalThis.File = window.File;
globalThis.Blob = window.Blob;
globalThis.FormData = window.FormData;
globalThis.Headers = window.Headers;
globalThis.Request = window.Request;
globalThis.Response = window.Response;
globalThis.URL = window.URL;
globalThis.URLSearchParams = window.URLSearchParams;
globalThis.AbortController = window.AbortController;
globalThis.getComputedStyle = window.getComputedStyle.bind(window);

if (typeof window.fetch === 'function') {
  globalThis.fetch = window.fetch.bind(window);
}
if (typeof window.requestAnimationFrame === 'function') {
  globalThis.requestAnimationFrame = window.requestAnimationFrame.bind(window);
}
if (typeof window.cancelAnimationFrame === 'function') {
  globalThis.cancelAnimationFrame = window.cancelAnimationFrame.bind(window);
}

await import('../web/src_ts/__tests__/setup.ts');
