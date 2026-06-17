import { useState, useRef, useEffect } from 'react'
import clsx from 'clsx'
import { TrendingUp, House, LayoutDashboard, Briefcase, Sun, Moon, RefreshCw } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import type { HealthStatus, LatencyRecord } from '../types'
import { useTheme } from '../contexts/ThemeContext'
import { etToLocalHHMM, localTzAbbr } from '../utils/time'

interface Props {
  healthStatus: HealthStatus
  latencyMs: number | null
  lastChecked: Date | null
  latencyHistory: LatencyRecord[]
  onRefreshHealth: () => Promise<void>
  marketOpen: boolean | null
  onRefreshMarket: () => Promise<void>
}

const NAV_ITEMS: Array<{
  path: string
  label: string
  icon: React.ElementType
  end?: boolean
}> = [
  { path: '/', label: 'Home', icon: House, end: true },
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/portfolio', label: 'Portfolio', icon: Briefcase },
]

const SESSIONS = [
  { label: 'Pre-market',  color: 'text-amber-400',   start: '04:00', end: '09:30' },
  { label: 'Regular',     color: 'text-emerald-400', start: '09:30', end: '16:00' },
  { label: 'After-hours', color: 'text-blue-400',    start: '16:00', end: '20:00' },
] as const

function latencyColor(ms: number | null): string {
  if (ms === null) return 'text-zinc-600'
  if (ms < 100) return 'text-emerald-400'
  if (ms < 300) return 'text-yellow-400'
  return 'text-red-400'
}

function latencyLabel(ms: number): string {
  if (ms < 100) return 'Excellent'
  if (ms < 300) return 'Good'
  return 'Slow'
}

export function Navbar({
  healthStatus, latencyMs, lastChecked, latencyHistory, onRefreshHealth,
  marketOpen, onRefreshMarket,
}: Props) {
  const { isDark, toggleTheme } = useTheme()
  const [showMarketPopup, setShowMarketPopup] = useState(false)
  const [showHealthPopup, setShowHealthPopup] = useState(false)
  const [refreshingMarket, setRefreshingMarket] = useState(false)
  const [refreshingHealth, setRefreshingHealth] = useState(false)
  const marketRef = useRef<HTMLDivElement>(null)
  const healthRef = useRef<HTMLDivElement>(null)
  const tz = localTzAbbr()

  useEffect(() => {
    if (!showMarketPopup) return
    const handler = (e: MouseEvent) => {
      if (!marketRef.current?.contains(e.target as Node)) setShowMarketPopup(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showMarketPopup])

  useEffect(() => {
    if (!showHealthPopup) return
    const handler = (e: MouseEvent) => {
      if (!healthRef.current?.contains(e.target as Node)) setShowHealthPopup(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showHealthPopup])

  async function handleMarketClick() {
    setShowMarketPopup(s => !s)
    setRefreshingMarket(true)
    try { await onRefreshMarket() } finally { setRefreshingMarket(false) }
  }

  async function handleMarketRefreshOnly(e: React.MouseEvent) {
    e.stopPropagation()
    if (refreshingMarket) return
    setRefreshingMarket(true)
    try { await onRefreshMarket() } finally { setRefreshingMarket(false) }
  }

  async function handleHealthRefresh(e: React.MouseEvent) {
    e.stopPropagation()
    if (refreshingHealth) return
    setRefreshingHealth(true)
    try { await onRefreshHealth() } finally { setRefreshingHealth(false) }
  }

  return (
    <header className="flex items-center h-14 px-6 border-b border-zinc-800 bg-zinc-950 shrink-0 gap-8">
      <div className="flex items-center gap-2.5">
        <TrendingUp size={18} className="text-indigo-400" />
        <span className="text-zinc-100 font-semibold tracking-tight">Market Lens</span>
      </div>

      <nav className="flex items-center gap-1">
        {NAV_ITEMS.map(({ path, label, icon: Icon, end }) => (
          <NavLink
            key={path}
            to={path}
            end={end}
            className={({ isActive }) => clsx(
              'flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
              isActive
                ? 'bg-zinc-800 text-zinc-100'
                : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900',
            )}
          >
            <Icon size={14} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-3">

        {/* Health status block */}
        <div className="relative" ref={healthRef}>
          <button
            onClick={() => setShowHealthPopup(s => !s)}
            className={clsx(
              'flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-colors',
              showHealthPopup
                ? 'border-zinc-700 bg-zinc-900 text-zinc-300'
                : 'border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:bg-zinc-900 hover:text-zinc-300',
            )}
          >
            <span
              className={clsx('w-2 h-2 rounded-full shrink-0', {
                'bg-emerald-500': healthStatus === 'ok',
                'bg-red-500': healthStatus === 'error',
                'bg-yellow-400 animate-pulse': healthStatus === 'loading',
              })}
            />
            {healthStatus === 'ok' ? 'API Online' : healthStatus === 'loading' ? 'API …' : 'API Offline'}
          </button>

          {showHealthPopup && (
            <div className="absolute right-0 top-full mt-2 z-50 w-72 bg-zinc-950 border border-zinc-700 rounded-xl p-4 shadow-2xl">
              <div className="flex items-center justify-between mb-3">
                <p className="text-[10px] font-semibold tracking-widest text-zinc-400">API HEALTH</p>
                <button
                  onClick={handleHealthRefresh}
                  disabled={refreshingHealth}
                  title="Refresh health status"
                  className="text-zinc-600 hover:text-zinc-400 disabled:opacity-40 transition-colors"
                >
                  <RefreshCw size={11} className={refreshingHealth ? 'animate-spin' : ''} />
                </button>
              </div>

              {/* Current status pill */}
              <div className="flex items-center gap-2 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 mb-4">
                <span
                  className={clsx('w-2 h-2 rounded-full shrink-0', {
                    'bg-emerald-500': healthStatus === 'ok',
                    'bg-red-500': healthStatus === 'error',
                    'bg-yellow-400 animate-pulse': healthStatus === 'loading',
                  })}
                />
                <span className="text-sm font-medium text-zinc-200">
                  {healthStatus === 'ok' ? 'Backend Online' : healthStatus === 'loading' ? 'Connecting…' : 'Backend Offline'}
                </span>
                {latencyMs !== null && (
                  <span className={clsx('ml-auto text-xs font-mono font-medium', latencyColor(latencyMs))}>
                    {latencyMs} ms
                  </span>
                )}
              </div>

              {/* Latency + last checked */}
              <div className="space-y-3 mb-4">
                {latencyMs !== null && (
                  <div className="space-y-0.5">
                    <span className="text-[10px] font-semibold tracking-widest text-zinc-500">LATENCY</span>
                    <div className="flex items-baseline gap-1.5">
                      <span className={clsx('font-mono text-xl font-semibold', latencyColor(latencyMs))}>
                        {latencyMs}
                      </span>
                      <span className="text-zinc-500 text-xs font-mono">ms</span>
                      <span className={clsx('text-xs font-medium', latencyColor(latencyMs))}>
                        · {latencyLabel(latencyMs)}
                      </span>
                    </div>
                  </div>
                )}
                {lastChecked && (
                  <div className="space-y-0.5">
                    <span className="text-[10px] font-semibold tracking-widest text-zinc-500">LAST CHECKED</span>
                    <p className="font-mono text-zinc-300 text-xs">{lastChecked.toLocaleTimeString()}</p>
                  </div>
                )}
              </div>

              {/* Recent checks */}
              {latencyHistory.length > 0 && (
                <div className="space-y-2">
                  <span className="text-[10px] font-semibold tracking-widest text-zinc-500">RECENT CHECKS</span>
                  <div className="space-y-1.5">
                    {[...latencyHistory].reverse().slice(0, 5).map((r, i) => (
                      <div key={i} className="flex items-center justify-between text-[11px] font-mono">
                        <span className="text-zinc-600">{r.time}</span>
                        <span className={clsx(
                          'flex items-center gap-1',
                          r.status === 'ok' ? 'text-emerald-400' : 'text-red-400',
                        )}>
                          <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', r.status === 'ok' ? 'bg-emerald-500' : 'bg-red-500')} />
                          {r.status === 'ok' ? 'Online' : 'Offline'}
                        </span>
                        <span className={latencyColor(r.latencyMs)}>
                          {r.latencyMs !== null ? `${r.latencyMs} ms` : '—'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <p className="mt-3 pt-3 border-t border-zinc-800 text-[10px] text-zinc-600">
                Auto-checks every 30 s
              </p>
            </div>
          )}
        </div>

        {/* Market status block */}
        <div className="relative" ref={marketRef}>
          <button
            onClick={handleMarketClick}
            className={clsx(
              'flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-colors',
              showMarketPopup
                ? 'border-zinc-700 bg-zinc-900 text-zinc-300'
                : 'border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:bg-zinc-900 hover:text-zinc-300',
            )}
          >
            <span
              className={clsx('w-2 h-2 rounded-full shrink-0', {
                'bg-emerald-500 animate-pulse': marketOpen === true,
                'bg-red-500': marketOpen === false,
                'bg-zinc-600': marketOpen === null,
              })}
            />
            {marketOpen === null ? 'Market —' : marketOpen ? 'Market Open' : 'Market Closed'}
            <RefreshCw
              size={10}
              className={clsx('shrink-0 transition-opacity', refreshingMarket ? 'animate-spin opacity-100' : 'opacity-30')}
            />
          </button>

          {showMarketPopup && (
            <div className="absolute right-0 top-full mt-2 z-50 w-72 bg-zinc-950 border border-zinc-700 rounded-xl p-4 shadow-2xl">
              <div className="flex items-center justify-between mb-3">
                <p className="text-[10px] font-semibold tracking-widest text-zinc-400">
                  NYSE MARKET HOURS
                </p>
                <button
                  onClick={handleMarketRefreshOnly}
                  disabled={refreshingMarket}
                  title="Refresh market status"
                  className="text-zinc-600 hover:text-zinc-400 disabled:opacity-40 transition-colors"
                >
                  <RefreshCw size={11} className={refreshingMarket ? 'animate-spin' : ''} />
                </button>
              </div>

              {/* Current status pill */}
              <div className="flex items-center gap-2 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 mb-4">
                <span
                  className={clsx('w-2 h-2 rounded-full shrink-0', {
                    'bg-emerald-500 animate-pulse': marketOpen === true,
                    'bg-red-500': marketOpen === false,
                    'bg-zinc-600': marketOpen === null,
                  })}
                />
                <span className="text-sm font-medium text-zinc-200">
                  {marketOpen === null ? 'Checking…' : marketOpen ? 'Market is Open' : 'Market is Closed'}
                </span>
              </div>

              {/* Session schedule */}
              <div className="space-y-3">
                {SESSIONS.map(({ label, color, start, end }) => (
                  <div key={label} className="space-y-0.5">
                    <span className={clsx('text-[10px] font-semibold tracking-widest', color)}>
                      {label.toUpperCase()}
                    </span>
                    <div className="flex items-center justify-between text-xs font-mono">
                      <span className="text-zinc-400">{start} – {end} ET</span>
                      <span className="text-zinc-300">
                        ({etToLocalHHMM(start)} – {etToLocalHHMM(end)} {tz})
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              <p className="mt-3 pt-3 border-t border-zinc-800 text-[10px] text-zinc-600">
                All sessions Eastern Time (ET) · Auto-refreshes every 5 min
              </p>
            </div>
          )}
        </div>

        {/* Theme toggle */}
        <button
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect()
            toggleTheme(rect.left + rect.width / 2, rect.top + rect.height / 2)
          }}
          title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          className="theme-toggle-btn flex items-center justify-center w-8 h-8 rounded-lg text-zinc-400"
        >
          {isDark ? <Sun size={14} /> : <Moon size={14} />}
        </button>
      </div>
    </header>
  )
}
