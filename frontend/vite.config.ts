import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

/**
 * Port allocation:
 *   :3000  — Vite dev server (this file)
 *   :8000  — Splunk Enterprise (DO NOT use — Splunk owns this port)
 *   :8001  — ARIA FastAPI backend  ← start with: uvicorn main:app --port 8001
 *   :8089  — Splunk management / MCP Server API
 *   :6379  — Redis
 *
 * All /api and /ws requests from the browser go to the Vite dev server (:3000).
 * Vite proxies them to the backend (:8001) server-side, adding the correct
 * host header. The browser never sees a cross-origin request, so CORS is
 * never triggered in development.
 */
export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },

  server: {
    port: 3000,
    strictPort: true,

    proxy: {
      // REST API
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        secure: false,
      },
      // WebSocket
      '/ws': {
        target: 'ws://127.0.0.1:8001',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
