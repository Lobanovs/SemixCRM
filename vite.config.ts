import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  server: {
    watch: {
      // backend/data держит живые профили Chrome, SQLite и рантайм парсера.
      // Заблокированный временный файл Chrome роняет watcher с EBUSY, а вместе
      // с ним и весь дев-сервер. Фронтенду эти файлы не нужны.
      ignored: [
        '**/backend/data/**',
        '**/backend/.venv/**',
        '**/backend/__pycache__/**',
      ],
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
