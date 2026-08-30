import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { createRequire } from 'module'

const require = createRequire(import.meta.url)
const cesiumModule = require('vite-plugin-cesium') as { default: (...args: any[]) => any }

export default defineConfig({
  plugins: [react(), cesiumModule.default()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 4000,
  },
})
