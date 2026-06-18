// DEPRECATED: The old JS tests imported from web/static/modules/, but those
// modules have been replaced by bridge shims that re-export from Vite build
// output (web/static/dist/assets/). The Vite bundles are entry-point scripts
// (not library modules), so named exports are tree-shaken away — the aliased
// imports fail at runtime.
//
// The real test suite is in web/src_ts/ — run with vitest.ts.config.js:
//   npx vitest --config vitest.ts.config.js
//
// Only exclude the known-broken tests below; remaining JS tests (contracts,
// specs, utils) may still pass and are kept for reference.

import { defineConfig } from 'vitest/config';
import { resolve } from 'path';

const BROKEN_JS_TESTS = [
  'test-api-client.test.js',
  'test-chat-stream.test.js',
  'test-content-handler.test.js',
  'test-debug.test.js',
  'test-dom-ordering.test.js',
  'test-frontend-integration.test.js',
  'test-retry-handler.test.js',
  'test-session.test.js',
  'test-stream-context.test.js',
  'test-stream-fetcher.test.js',
  'test-stream-renderer.test.js',
  'test-stream-retry-coordinator.test.js',
  'test-widget-init.test.js',
  'test-widget-system.test.js',
  'test-anti-regression-ui.test.js',
].map(f => `tests/${f}`);

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['tests/*.test.js'],
    exclude: BROKEN_JS_TESTS,
    testTimeout: 10000,
  },
  resolve: {
    alias: {
      '/static/dist/assets': resolve(__dirname, 'web/static/dist/assets'),
    },
  },
});
