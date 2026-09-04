import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Servido pelo FastAPI em /ops (SPA fallback). Em dev, a API vem do backend local.
export default defineConfig({
  plugins: [react()],
  base: '/ops/',
  build: { outDir: 'dist', sourcemap: false, emptyOutDir: true },
  server: {
    port: 5173,
    proxy: { '/ops/api': { target: 'http://127.0.0.1:8790', changeOrigin: false } },
  },
})
