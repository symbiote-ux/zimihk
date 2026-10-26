import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
  build: { chunkSizeWarningLimit: 800 }, // ponytail: echarts core is ~600 kB; code-split if the app grows
})
