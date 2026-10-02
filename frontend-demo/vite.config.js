import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Demo UI. Same rule as the main frontend: the browser never touches a
// database or a file. Everything goes through /api, proxied to FastAPI.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5174,
    strictPort: true,
    allowedHosts: true,
    hmr: { clientPort: 443, protocol: 'wss' },
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
