import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'happy-dom',
    setupFiles: ['./tests/setup.ts'],
    include: ['./tests/**/*.test.ts'],
    /*
     * One clock for everybody.
     *
     * Anything that renders an instant renders it in the machine's zone, so a
     * suite that does not pin one is asserting against wherever it happens to
     * run. CI is UTC and a laptop is not, which is a difference nobody wants to
     * debug from a failing assertion about a time.
     */
    env: { TZ: 'UTC' },
  },
})
