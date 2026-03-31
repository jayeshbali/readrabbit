import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Clerk v5 uses private class fields (#field syntax). Without esnext target,
  // esbuild/Rollup downlevels these and breaks Clerk's internal class hierarchy
  // (MessageChannel classes), causing React error #300 in production.
  build: {
    target: 'esnext',
  },
  optimizeDeps: {
    esbuildOptions: {
      target: 'esnext',
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
