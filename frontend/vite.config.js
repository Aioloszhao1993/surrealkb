import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发时代理后端，避免跨域；生产可用 Nginx 反代
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/media': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
