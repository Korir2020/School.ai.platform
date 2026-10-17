import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react()],
  server: { allowedHosts: ['.manus.computer'], proxy: { '/api': { target: process.env.VITE_API_TARGET || 'https://school-ai-platform.onrender.com', changeOrigin: true,
        configure: (p) => p.on('proxyReq', (r) => r.removeHeader('origin')) } } },
})
