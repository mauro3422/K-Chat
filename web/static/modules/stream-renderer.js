export function initStreamRenderer() {
  if (typeof KairosStream === 'undefined') {
    console.error('KairosStream not defined');
    return;
  }
}

initStreamRenderer();
