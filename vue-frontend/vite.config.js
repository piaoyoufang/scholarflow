import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Markdown from 'unplugin-vue-markdown/vite'

export default defineConfig({
  plugins: [
    vue({ include: [/\.vue$/, /\.md$/] }),
    Markdown({
      markdownItOptions: {
        html: false,
        linkify: true,
        typographer: true
      },
      wrapperClasses: 'markdown-body'
    })
  ],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  },
  // Vitest 配置：happy-dom 提供 localStorage 等浏览器 API（auth store 测试依赖它）
  test: {
    environment: 'happy-dom'
  }
})
