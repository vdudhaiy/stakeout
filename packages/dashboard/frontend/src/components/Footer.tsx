import { Github, ExternalLink, Bug } from 'lucide-react'

const REPO_URL   = 'https://github.com/vdudhaiy/market-lens'
const ISSUES_URL = 'https://github.com/vdudhaiy/market-lens/issues'
const YFINANCE_URL = 'https://github.com/ranaroussi/yfinance'

export function Footer() {
  return (
    <footer className="shrink-0 border-t border-zinc-800 bg-zinc-950 px-6 py-3.5">
      <div className="flex items-center justify-between gap-8 text-[11px]">

        {/* Brand + tagline */}
        <div className="flex flex-col gap-0.5 shrink-0">
          <div className="flex items-center gap-1.5">
            <svg width="12" height="12" viewBox="0 0 32 32" aria-hidden="true"><path d="M6 24l7-10 5 5 8-13" stroke="#E4B95B" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" fill="none"/></svg>
            <span className="font-display font-semibold text-zinc-300">Stakeout</span>
            <span className="font-mono text-[10px] leading-none text-zinc-600 border border-zinc-800 rounded px-1.5 py-px">
              v0.1.0
            </span>
          </div>
          <span className="text-zinc-600 pl-[19px]">Open markets, open source.</span>
        </div>

        {/* Disclaimer */}
        <p className="text-zinc-600 text-center leading-relaxed">
          Market data from Yahoo Finance via{' '}
          <a
            href={YFINANCE_URL}
            target="_blank"
            rel="noreferrer"
            className="text-zinc-500 underline underline-offset-2 hover:text-zinc-300 transition-colors"
          >
            yfinance
          </a>
          ; headlines via GDELT; FX via Frankfurter (ECB). For informational purposes
          only — not financial advice. Data may be delayed up to 15 minutes.
        </p>

        {/* Repo + issues + stack */}
        <div className="flex flex-col items-end gap-1 shrink-0">
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 text-zinc-500 hover:text-indigo-400 transition-colors group"
          >
            <Github size={11} />
            <span>vdudhaiy/market-lens</span>
            <ExternalLink size={9} className="opacity-0 group-hover:opacity-100 transition-opacity" />
          </a>
          <a
            href={ISSUES_URL}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 text-zinc-600 hover:text-red-400 transition-colors"
          >
            <Bug size={10} />
            <span>Report a bug or request a feature</span>
          </a>
          <span className="text-zinc-700">
            React · FastAPI · yfinance · © {new Date().getFullYear()}
          </span>
        </div>

      </div>
    </footer>
  )
}
