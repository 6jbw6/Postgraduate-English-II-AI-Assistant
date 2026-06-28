import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * Vite 构建配置
 * 
 * 开发模式：
 *   - 前端运行在 5173 端口（Vite 默认）
 *   - 通过 proxy 将 /api 请求转发到后端的 8000 端口
 *   - 避免跨域问题，无需额外配置 CORS
 * 
 * 生产模式：
 *   - npm run build 将构建产物输出到 dist/
 *   - 将 dist/ 内容复制到 frontend/ 根目录
 *   - 后端 FastAPI 直接提供静态文件服务
 */
export default defineConfig({
  plugins: [vue()],

  // 开发服务器配置
  server: {
    port: 5173,
    proxy: {
      // 将 /api 开头的请求代理到后端
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
