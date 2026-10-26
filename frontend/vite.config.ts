/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const api = { '/api': 'http://localhost:8000' }

export default defineConfig({
  plugins: [react()],
  server: { proxy: api },
  build: { chunkSizeWarningLimit: 800 }, // ponytail: echarts core is ~600 kB; code-split if the app grows
  test: { include: ['src/**/*.test.ts'] },
})
