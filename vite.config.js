import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  root: 'web/static',
  base: '/static/dist/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(__dirname, 'web/static/app.js'),
      output: {
        entryFileNames: 'assets/app.js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        ws: true,
        // Prevent buffering for SSE streaming
        proxyReqWs: undefined,
      },
      '/sidebar': {
        target: 'http://localhost:8000',
        ws: true,
      },
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
