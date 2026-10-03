import { fileURLToPath, URL } from 'node:url'
import { readFileSync } from 'node:fs'
import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'

// 运行参数的唯一来源是仓库根的 runtime.json：端口、代理目标、跨域白名单、
// 页大小上限前后端共用这一份，改完两边同时生效。
// 老的环境变量 VITE_PROXY_TARGET 仍可覆盖代理目标。
const runtimePath = fileURLToPath(new URL('../runtime.json', import.meta.url))

interface RuntimeConfig {
  backend?: { host?: string; port?: number }
  frontend?: { host?: string; port?: number }
  proxy_target?: string
}

function loadRuntime(): RuntimeConfig {
  try {
    return JSON.parse(readFileSync(runtimePath, 'utf-8')) as RuntimeConfig
  } catch {
    return {}
  }
}

const runtime = loadRuntime()
const backendHost = runtime.backend?.host ?? '127.0.0.1'
const backendPort = runtime.backend?.port ?? 8000
// 代理目标缺省跟随后端地址派生，保证端口只维护一份
const proxyTarget = process.env.VITE_PROXY_TARGET ?? runtime.proxy_target ?? `http://${backendHost}:${backendPort}`
const devHost = runtime.frontend?.host ?? '127.0.0.1'
const devPort = runtime.frontend?.port ?? 5173

// runtime.json 变更时重启 dev server，让新端口/代理目标立即生效，
// 与后端的热重载配合，两边同时切到新的一份
function runtimeReload(): Plugin {
  return {
    name: 'runtime-config-reload',
    configureServer(server) {
      server.watcher.add(runtimePath)
      const restartOnChange = (file: string) => {
        if (file === runtimePath) {
          server.restart()
        }
      }
      server.watcher.on('change', restartOnChange)
      server.watcher.on('add', restartOnChange)
    },
  }
}

export default defineConfig({
  plugins: [vue(), runtimeReload()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: devHost,
    port: devPort,
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
})
