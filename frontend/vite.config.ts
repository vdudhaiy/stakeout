import { readFileSync } from 'fs'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import type { IncomingMessage } from 'http'

const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8'))

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
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    proxy: {
      '/stocks': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      '/health': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      // Listed explicitly and before '/portfolio'. Vite matches these keys by
      // prefix, so '/portfolio' would happen to swallow '/portfolios' too —
      // but nginx's equivalent regex anchors on (/|$) and does not, so
      // relying on that overlap makes dev and Docker disagree.
      '/portfolios': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      '/portfolio': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      '/indicators': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      '/watchlist': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      '/news': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      '/fx': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      '/ai': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      '/auth': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
      '/account': { target: 'http://localhost:8000', bypass: bypassHtmlNavigations },
    },
  },
})
