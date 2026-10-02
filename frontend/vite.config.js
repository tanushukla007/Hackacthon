import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The frontend NEVER talks to a database. Everything goes through /api,
// proxied to the FastAPI backend, so the browser only ever needs one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    hmr: { clientPort: 443, protocol: 'wss' },
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
