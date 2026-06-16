import { defineConfig } from 'vitest/config';
export default defineConfig({
  test: {
    globals: true,
    environment: 'happy-dom',
    include: ['web/src_ts/**/*.test.ts'],
    setupFiles: ['web/src_ts/__tests__/setup.ts'],
    testTimeout: 10000,
  },
});
