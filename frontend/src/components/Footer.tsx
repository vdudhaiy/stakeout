import { Github, ExternalLink, Bug } from 'lucide-react'

const REPO_URL   = 'https://github.com/vdudhaiy/stakeout'
const ISSUES_URL = 'https://github.com/vdudhaiy/stakeout/issues'
const YFINANCE_URL = 'https://github.com/ranaroussi/yfinance'

export function Footer() {
  return (
    <footer className="shrink-0 border-t border-zinc-800 bg-zinc-950 px-4 sm:px-6 py-3 sm:py-3.5">
      {/* Three columns side by side once there's room; stacked and centred on
          phones, where 8rem of gutter between them isn't available. */}
      <div className="flex flex-col lg:flex-row items-center lg:items-center justify-between gap-2 lg:gap-8 text-[0.6875rem]">

        {/* Brand + tagline */}
        <div className="flex flex-col items-center lg:items-start gap-0.5 shrink-0">
          <div className="flex items-center gap-1.5">
            <svg width="12" height="12" viewBox="0 0 32 32" aria-hidden="true"><path d="M6 24l7-10 5 5 8-13" stroke="#E4B95B" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" fill="none"/></svg>
            <span className="font-display font-semibold text-zinc-300">Stakeout</span>
            <span className="font-mono text-[0.625rem] leading-none text-zinc-600 border border-zinc-800 rounded px-1.5 py-px">
              v{__APP_VERSION__}
            </span>
          </div>
          <span className="hidden lg:block text-zinc-600 lg:pl-[1.1875rem]">Open markets, open source.</span>
        </div>

        {/* Disclaimer — the long-form version is desktop-only; phones get the
            same obligations in one line rather than a five-line wall. */}
        <p className="hidden sm:block text-zinc-600 text-center leading-relaxed">
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

        <p className="sm:hidden text-zinc-600 text-center leading-relaxed">
          Data via yfinance &amp; GDELT · not financial advice
        </p>

        {/* Repo + issues + stack */}
        <div className="flex flex-row lg:flex-col flex-wrap justify-center items-center lg:items-end gap-x-4 gap-y-1 shrink-0">
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            className="tap-target flex items-center gap-1 text-zinc-500 hover:text-indigo-400 transition-colors group"
          >
            <Github size={11} />
            <span>vdudhaiy/stakeout</span>
            <ExternalLink size={9} className="opacity-0 group-hover:opacity-100 transition-opacity" />
          </a>
          <a
            href={ISSUES_URL}
            target="_blank"
            rel="noreferrer"
            className="tap-target flex items-center gap-1 text-zinc-600 hover:text-red-400 transition-colors"
          >
            <Bug size={10} />
            <span className="hidden sm:inline">Report a bug or request a feature</span>
            <span className="sm:hidden">Report a bug</span>
          </a>
          <span className="hidden lg:inline text-zinc-700">
            React · FastAPI · yfinance · © {new Date().getFullYear()}
          </span>
        </div>

      </div>
    </footer>
  )
}
