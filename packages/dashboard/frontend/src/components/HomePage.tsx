import { ArrowRight, BarChart2, Briefcase, Bug, Github, LineChart, Newspaper, Star, Users } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { NewsPanel } from './NewsPanel'

const FEATURES = [
  {
    icon: LineChart,
    title: 'Charts & indicators',
    description:
      'Candlestick and area charts from 1-day intraday to 3 years, with SMA/EMA overlays, Bollinger Bands, RSI and MACD — every stat explained in plain language.',
  },
  {
    icon: Briefcase,
    title: 'Two-market portfolios',
    description:
      'Track US and Indian holdings side by side with FIFO cost basis, realized and unrealized P&L, allocation breakdowns, and one-click Excel export.',
  },
  {
    icon: BarChart2,
    title: 'Analyst insights',
    description:
      'Price-target ranges with upside math, buy/hold/sell recommendation drift, and EPS & revenue estimates for upcoming quarters.',
  },
  {
    icon: Users,
    title: 'Your account, anywhere',
    description:
      'Sign in with Google or email to sync your watchlist and portfolios across devices — or run it locally with no account at all.',
  },
]

const fadeUp = {
  hidden: { opacity: 0, y: 14 },
  show: (i: number) => ({ opacity: 1, y: 0, transition: { delay: 0.08 * i, duration: 0.45, ease: 'easeOut' as const } }),
}

export function HomePage() {
  const navigate = useNavigate()

  return (
    <div className="flex-1 overflow-y-auto">
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div className="relative overflow-hidden">
        {/* faint candlestick backdrop */}
        <svg
          aria-hidden="true"
          className="absolute inset-x-0 bottom-0 w-full h-40 opacity-[0.07] pointer-events-none"
          viewBox="0 0 1200 160" preserveAspectRatio="none"
        >
          {Array.from({ length: 40 }).map((_, i) => {
            const x = i * 30 + 8
            const h = 30 + ((i * 37) % 90)
            const y = 150 - h
            const up = i % 3 !== 0
            return (
              <g key={i}>
                <line x1={x + 6} y1={y - 8} x2={x + 6} y2={y + h + 8} stroke={up ? '#2FBF71' : '#E5484D'} strokeWidth="1.5" />
                <rect x={x} y={y} width="12" height={h} fill={up ? '#2FBF71' : '#E5484D'} rx="1" />
              </g>
            )
          })}
        </svg>

        <div className="relative flex flex-col items-center text-center px-6 pt-16 pb-14">
          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={0}>
            <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-indigo-500/30 bg-indigo-500/10 text-indigo-300 text-[11px] font-mono tracking-wide mb-6">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
              Free · Open source · US + India
            </span>
          </motion.div>

          <motion.h1
            variants={fadeUp} initial="hidden" animate="show" custom={1}
            className="font-display text-5xl font-bold tracking-tight text-zinc-100 mb-3"
          >
            Stakeout
          </motion.h1>

          <motion.p
            variants={fadeUp} initial="hidden" animate="show" custom={2}
            className="font-mono text-sm tracking-[0.25em] uppercase text-indigo-400 mb-5"
          >
            Open markets, open source
          </motion.p>

          <motion.p
            variants={fadeUp} initial="hidden" animate="show" custom={3}
            className="text-zinc-400 text-lg leading-relaxed max-w-xl mb-8"
          >
            Keep watch on your stakes across NYSE, NASDAQ, NSE and BSE — charts,
            portfolios, analyst views and headlines, with no subscription and no
            terminal fee. Fork it, self-host it, make it yours.
          </motion.p>

          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={4} className="flex items-center gap-3">
            <button
              onClick={() => navigate('/dashboard')}
              className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Explore the dashboard
              <ArrowRight size={14} />
            </button>
            <button
              onClick={() => navigate('/portfolio')}
              className="flex items-center gap-2 px-5 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 rounded-lg text-sm font-medium transition-colors"
            >
              <Briefcase size={14} />
              My portfolios
            </button>
          </motion.div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 pb-16 space-y-10">
        {/* ── Headlines: US + India ────────────────────────────────────────── */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Newspaper size={14} className="text-indigo-400" />
            <h2 className="font-display text-sm font-semibold text-zinc-200 tracking-wide">Today on the markets</h2>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <NewsPanel mode={{ kind: 'market', region: 'us' }} limit={6} />
            <NewsPanel mode={{ kind: 'market', region: 'in' }} limit={6} />
          </div>
        </div>

        {/* ── Feature cards ────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {FEATURES.map(({ icon: Icon, title, description }, i) => (
            <motion.div
              key={title}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-40px' }}
              transition={{ delay: i * 0.07, duration: 0.4 }}
              className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-3 hover:border-zinc-700 transition-colors"
            >
              <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
                <Icon size={18} className="text-indigo-400" />
              </div>
              <h3 className="font-display text-zinc-100 font-semibold">{title}</h3>
              <p className="text-zinc-500 text-sm leading-relaxed">{description}</p>
            </motion.div>
          ))}
        </div>

        {/* ── Open source / feedback ───────────────────────────────────────── */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-5 py-4 flex items-center justify-between gap-6">
          <div className="flex items-start gap-3">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 shrink-0 mt-0.5">
              <Github size={15} className="text-indigo-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-zinc-200 mb-0.5">Free &amp; open source</p>
              <p className="text-xs text-zinc-500 leading-relaxed">
                If Stakeout has been useful to you, the best way to support the project
                is to <span className="text-zinc-300 font-medium">star the repo on GitHub</span> — it helps
                others discover it. Found a bug or have a feature idea? Open an issue.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <a
              href="https://github.com/vdudhaiy/stakeout"
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 border border-indigo-500 text-white text-xs font-medium transition-colors"
            >
              <Star size={12} />
              Star on GitHub
            </a>
            <a
              href="https://github.com/vdudhaiy/stakeout/issues/new"
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-300 text-xs font-medium transition-colors"
            >
              <Bug size={12} />
              Open an issue
            </a>
          </div>
        </div>

        {/* ── Disclaimer ───────────────────────────────────────────────────── */}
        <div className="border border-amber-500/20 bg-amber-500/5 rounded-xl px-5 py-4 text-xs text-zinc-500 leading-relaxed space-y-1">
          <p>
            <span className="text-amber-400 font-semibold">Not financial advice.</span>{' '}
            Stakeout is for informational and educational purposes only. Nothing shown here
            constitutes financial, investment, or trading advice. Always consult a qualified
            financial professional before making investment decisions.
          </p>
          <p>
            <span className="text-amber-400 font-semibold">Data sources.</span>{' '}
            Market data is fetched via{' '}
            <a href="https://github.com/ranaroussi/yfinance" target="_blank" rel="noreferrer" className="text-zinc-400 underline underline-offset-2 hover:text-zinc-300">yfinance</a>{' '}
            (Yahoo Finance); headlines via the{' '}
            <a href="https://www.gdeltproject.org/" target="_blank" rel="noreferrer" className="text-zinc-400 underline underline-offset-2 hover:text-zinc-300">GDELT Project</a>;
            {' '}FX rates via{' '}
            <a href="https://frankfurter.dev/" target="_blank" rel="noreferrer" className="text-zinc-400 underline underline-offset-2 hover:text-zinc-300">Frankfurter</a> (ECB).
            Data may be delayed, incomplete, or inaccurate and is intended for personal, non-commercial use only.
          </p>
        </div>
      </div>
    </div>
  )
}
