import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/stocks': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/portfolio': 'http://localhost:8000',
      '/indicators': 'http://localhost:8000',
      '/watchlist': 'http://localhost:8000',
      '/news': 'http://localhost:8000',
      '/fx': 'http://localhost:8000',
    },
  },
})
