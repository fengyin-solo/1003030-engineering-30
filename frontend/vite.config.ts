import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// 运行参数（端口、代理目标、跨域白名单、页大小上限）统一维护在仓库根目录 .env，
// 前后端都读这一份。envDir 指到根目录后，.env 一改 vite 会自动重启 dev server，
// 代理目标跟着新端口走，不会一边改了另一边还按老的跑。
// 老的环境变量 VITE_PROXY_TARGET 仍然优先，可临时把代理指向别的后端。
const envDir = fileURLToPath(new URL('..', import.meta.url))

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, envDir, '')
  const backendPort = env.APP_PORT || '8000'
  const proxyTarget = env.VITE_PROXY_TARGET || `http://127.0.0.1:${backendPort}`

  return {
    envDir,
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      // 关掉自动打开页面：起服务时只打印地址，不拉起浏览器
      open: false,
      strictPort: false,
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
    },
  }
})
