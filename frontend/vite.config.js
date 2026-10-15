import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 构建时间戳（东八区，分钟精度）。注入到前端，显示在页脚，
// 用来一眼确认「浏览器里跑的是哪一版」——排查「改了没生效 / 缓存」时非常省事。
function buildStamp() {
  const d = new Date(Date.now() + 8 * 3600 * 1000)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`
}

// 开发时代理后端，避免跨域；生产可用 Nginx 反代
export default defineConfig({
  plugins: [react()],
  define: {
    __BUILD_STAMP__: JSON.stringify(buildStamp()),
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/media': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
