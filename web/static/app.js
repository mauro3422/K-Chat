// Legacy compatibility shim.
// The real application bootstrap now lives in the TypeScript bundle.

import('/static/dist/assets/app_mock.js').catch((err) => {
  console.warn('Kairos TS bundle unavailable', err);
});
