import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  test: {
    environment: 'happy-dom',
  },
  server: {
    port: 5173,
    proxy: {
      // SSE 端点：必须关闭 vite/http-proxy 默认的响应缓冲，否则 reader.read()
      // 拿不到 EOF，await fetch 永不返回 → 前端"生成中..."按钮卡死、回复不显示。
      //
      // 单文档编辑响应快/包少时掩盖，方案构建响应慢/包多时暴露（v0.0.0+ 一直存在）。
      //
      // 解决：selfHandleResponse=true 让 vite 把响应交给我们的回调，
      // 手动把上游响应原样 pipe 到客户端 socket，不经过 http-proxy 内部缓冲。
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        selfHandleResponse: true,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes, req, res) => {
            res.statusCode = proxyRes.statusCode || 502
            for (const [k, v] of Object.entries(proxyRes.headers)) {
              const lk = k.toLowerCase()
              if (lk === 'transfer-encoding' || lk === 'connection') continue
              res.setHeader(k, v)
            }
            if (req.socket) {
              req.socket.setNoDelay(true)
              req.socket.setTimeout(0)
            }
            proxyRes.on('data', (chunk) => res.write(chunk))
            proxyRes.on('end', () => res.end())
            proxyRes.on('error', (err) => {
              try { res.end() } catch {}
              console.error('[vite-proxy] upstream error:', err.message)
            })
          })
          proxy.on('error', (err, _req, res) => {
            console.error('[vite-proxy] error:', err.message)
            if (res && !res.headersSent) {
              res.writeHead(502, { 'Content-Type': 'text/plain' })
              res.end('proxy error: ' + err.message)
            }
          })
        },
      },
    },
  },
})
