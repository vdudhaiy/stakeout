import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import type { IncomingMessage } from 'http'

// '/portfolio' is both a backend API prefix and a client-side SPA route.
// Without this, a full page load/reload on /portfolio (or any deep link to
// it) gets swallowed by the proxy and returns raw backend JSON instead of
// the app shell. Only bypass (skip proxying, fall through to the SPA) for
// browser navigations — actual API calls from the app send an XHR/fetch
// Accept header, not `text/html`.
function bypassHtmlNavigations(req: IncomingMessage) {
  if (req.headers.accept?.includes('text/html')) return '/index.html'
}

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/stocks': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      '/health': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      '/portfolio': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      '/indicators': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      '/watchlist': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      '/news': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      '/fx': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      '/auth': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
    },
  },
})
