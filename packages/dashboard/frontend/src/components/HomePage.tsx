import { TrendingUp, BarChart2, Activity, ArrowRight, LineChart, Briefcase } from 'lucide-react'
import type { View } from '../types'

interface Props {
  onNavigate: (v: Extract<View, 'dashboard' | 'health' | 'portfolio'>) => void
}

const FEATURES = [
  {
    icon: LineChart,
    title: 'Price Charts',
    description:
      'OHLCV price and volume charts with selectable time ranges from 1 day to 3 years, backed by archived market data and live intraday feeds.',
  },
  {
    icon: Briefcase,
    title: 'Portfolio Tracking',
    description:
      'Log buys and sells, track unrealized and realized P&L with FIFO cost basis, and monitor performance across all your positions in one view.',
  },
  {
    icon: BarChart2,
    title: 'Analyst Insights',
    description:
      'Analyst price targets with upside calculations, buy/hold/sell recommendation breakdowns, and earnings and revenue estimates per ticker.',
  },
  {
    icon: Activity,
    title: 'Health Monitoring',
    description:
      'Live backend status with per-request latency tracking, colour-coded thresholds, and a rolling history of health checks.',
  },
]

export function HomePage({ onNavigate }: Props) {
  return (
    <div className="flex-1 overflow-y-auto">
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div className="flex flex-col items-center text-center px-6 pt-20 pb-14">
        <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 mb-6">
          <TrendingUp size={30} className="text-indigo-400" />
        </div>

        <h1 className="text-4xl font-bold tracking-tight text-white mb-4">Market Lens</h1>

        <p className="text-zinc-400 text-lg leading-relaxed max-w-xl mb-8">
          A personal investment dashboard for exploring stock price history,
          tracking your portfolio positions, and surfacing analyst insights —
          all in one place.
        </p>

        <div className="flex items-center gap-3">
          <button
            onClick={() => onNavigate('dashboard')}
            className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Explore Dashboard
            <ArrowRight size={14} />
          </button>
          <button
            onClick={() => onNavigate('portfolio')}
            className="flex items-center gap-2 px-5 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 rounded-lg text-sm font-medium transition-colors"
          >
            <Briefcase size={14} />
            My Portfolio
          </button>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 pb-16 space-y-10">
        {/* ── Feature cards ────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {FEATURES.map(({ icon: Icon, title, description }) => (
            <div
              key={title}
              className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-3"
            >
              <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
                <Icon size={18} className="text-indigo-400" />
              </div>
              <h3 className="text-white font-semibold">{title}</h3>
              <p className="text-zinc-500 text-sm leading-relaxed">{description}</p>
            </div>
          ))}
        </div>

        {/* ── Disclaimer ───────────────────────────────────────────────────── */}
        <div className="border border-amber-500/20 bg-amber-500/5 rounded-xl px-5 py-4 text-xs text-zinc-500 leading-relaxed space-y-1">
          <p>
            <span className="text-amber-400 font-semibold">Not financial advice.</span>{' '}
            Market Lens is for informational and educational purposes only. Nothing shown here
            constitutes financial, investment, or trading advice. Always consult a qualified
            financial professional before making investment decisions.
          </p>
          <p>
            <span className="text-amber-400 font-semibold">Data source.</span>{' '}
            Market data is fetched via{' '}
            <a
              href="https://github.com/ranaroussi/yfinance"
              target="_blank"
              rel="noreferrer"
              className="text-zinc-400 underline underline-offset-2 hover:text-zinc-300"
            >
              yfinance
            </a>{' '}
            (Yahoo Finance). Data may be delayed, incomplete, or inaccurate and is intended
            for personal, non-commercial use only.
          </p>
        </div>
      </div>
    </div>
  )
}
