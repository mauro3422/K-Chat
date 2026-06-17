import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  root: 'web/static',
  base: '/static/dist/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: process.env.NODE_ENV === 'development' ? true : false,
    rollupOptions: {
      input: {
        app_mock: resolve(__dirname, 'web/src_ts/app_mock.ts'),
        skills_ui: resolve(__dirname, 'web/static/modules/skills-ui.ts'),
        chat_form: resolve(__dirname, 'web/src_ts/core/ui/ChatForm.ts'),
        logger: resolve(__dirname, 'web/static/modules/logger.ts'),
        api_client: resolve(__dirname, 'web/static/modules/api-client.ts'),
        session_context: resolve(__dirname, 'web/static/modules/session-context.ts'),
        reasoning_handler: resolve(__dirname, 'web/static/modules/reasoning-handler.ts'),
        widget_container_renderer: resolve(__dirname, 'web/static/modules/widget-container-renderer.ts'),
        stream_error_handler: resolve(__dirname, 'web/static/modules/stream-error-handler.ts'),
      },
      output: {
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name][extname]',
        manualChunks(id) {
          if (id.includes('src_ts/widgets/') || id.includes('CanvasWorkspace') || id.includes('SkillsUI')) return 'widgets';
          if (id.includes('src_ts/streaming/')) return 'streaming';
          if (id.includes('src_ts/rendering/')) return 'rendering';
          if (id.includes('src_ts/core/debug') || id.includes('DebugManager')) return 'debug';
        },
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
