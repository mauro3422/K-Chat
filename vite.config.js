import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  root: 'web/static',
  build: {
    outDir: '../../dist/static',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        app: resolve(__dirname, 'web/static/main.js'),
      },
    },
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/sidebar': 'http://localhost:8000',
      '/sessions': 'http://localhost:8000',
      '/chat': 'http://localhost:8000',
      '/debug': 'http://localhost:8000',
    },
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'web/static'),
    },
  },
});
