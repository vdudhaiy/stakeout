import { useState, useRef, useEffect } from 'react'
import clsx from 'clsx'
import { House, LineChart, Briefcase, Sun, Moon, RefreshCw, LogOut, UserRound, Settings, Compass } from 'lucide-react'
import { NavLink, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'motion/react'
import { useTheme } from '../contexts/ThemeContext'
import { useAuth } from '../contexts/AuthContext'
import { AuthModal } from './AuthModal'
import { InfoTip } from './InfoTip'
import { etToLocalHHMM, istToLocalHHMM, localTzAbbr } from '../utils/time'
import { MARKET_STATUS_REFRESH_MS, formatInterval } from '../utils/env'
import { popIn } from '../lib/motion'

interface Props {
  marketOpen: boolean | null      // US (NYSE/NASDAQ)
  marketOpenIN: boolean | null    // India (NSE/BSE)
  onRefreshMarket: () => Promise<void>
}

const NAV_ITEMS: Array<{ path: string; label: string; icon: React.ElementType; end?: boolean }> = [
  { path: '/', label: 'Home', icon: House, end: true },
  { path: '/tracker', label: 'Tracker', icon: LineChart },
  { path: '/portfolio', label: 'Portfolio', icon: Briefcase },
  { path: '/get-started', label: 'Get Started', icon: Compass },
]

const US_SESSIONS = [
  { label: 'Pre-market',  color: 'text-amber-400',   start: '04:00', end: '09:30' },
  { label: 'Regular',     color: 'text-emerald-400', start: '09:30', end: '16:00' },
  { label: 'After-hours', color: 'text-blue-400',    start: '16:00', end: '20:00' },
] as const

const IN_SESSIONS = [
  { label: 'Pre-open', color: 'text-amber-400',   start: '09:00', end: '09:15' },
  { label: 'Regular',  color: 'text-emerald-400', start: '09:15', end: '15:30' },
  { label: 'Closing',  color: 'text-blue-400',    start: '15:40', end: '16:00' },
] as const

function StatusDot({ open }: { open: boolean | null }) {
  return (
    <span
      className={clsx('w-2 h-2 rounded-full shrink-0', {
        'bg-emerald-500 animate-pulse': open === true,
        'bg-red-500': open === false,
        'bg-zinc-600': open === null,
      })}
    />
  )
}

/** The Stakeout wordmark: a candle-wick spark over the name. */
function Wordmark() {
  return (
    <NavLink to="/" className="flex items-center gap-2.5 group">
      <svg width="20" height="20" viewBox="0 0 32 32" aria-hidden="true" className="shrink-0">
        <rect width="32" height="32" rx="7" className="fill-zinc-800 group-hover:fill-zinc-700 transition-colors" />
        <path d="M9 21l4-6 3 3 5-8" stroke="#E4B95B" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <circle cx="21" cy="10" r="2" fill="#E4B95B" />
      </svg>
      <span className="flex flex-col leading-none">
        <span className="font-display text-zinc-100 font-semibold tracking-tight text-[15px]">Stakeout</span>
        <span className="text-[8.5px] tracking-[0.18em] text-zinc-600 uppercase mt-0.5">Open markets, open source</span>
      </span>
    </NavLink>
  )
}

export function Navbar({
  marketOpen, marketOpenIN, onRefreshMarket,
}: Props) {
  const { isDark, toggleTheme } = useTheme()
  const { user, isGuest, localAuthMode, signOut } = useAuth()
  const navigate = useNavigate()
  const [showMarketPopup, setShowMarketPopup] = useState(false)
  const [showUser, setShowUser] = useState(false)
  const [showAuthModal, setShowAuthModal] = useState(false)
  const [refreshingMarket, setRefreshingMarket] = useState(false)
  const marketRef = useRef<HTMLDivElement>(null)
  const userRef = useRef<HTMLDivElement>(null)
  const tz = localTzAbbr()

  useEffect(() => {
    const popups: Array<[boolean, React.RefObject<HTMLDivElement>, (v: boolean) => void]> = [
      [showMarketPopup, marketRef, setShowMarketPopup],
      [showUser, userRef, setShowUser],
    ]
    const active = popups.filter(([open]) => open)
    if (active.length === 0) return
    const handler = (e: MouseEvent) => {
      for (const [, ref, set] of active) {
        if (!ref.current?.contains(e.target as Node)) set(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showMarketPopup, showUser])

  async function handleMarketClick() {
    setShowMarketPopup(s => !s)
    setRefreshingMarket(true)
    try { await onRefreshMarket() } finally { setRefreshingMarket(false) }
  }

  const anyOpen = marketOpen === true || marketOpenIN === true
  const bothKnown = marketOpen !== null && marketOpenIN !== null

  return (
    <header className="flex items-center h-14 px-6 border-b border-zinc-800 bg-zinc-950 shrink-0 gap-8">
      <Wordmark />

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

        {/* Markets status (US + India) */}
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
            <span className="flex items-center gap-1">
              <StatusDot open={marketOpen} />
              <span className="font-mono text-[10px] text-zinc-500">US</span>
            </span>
            <span className="flex items-center gap-1">
              <StatusDot open={marketOpenIN} />
              <span className="font-mono text-[10px] text-zinc-500">IN</span>
            </span>
            {bothKnown ? (anyOpen ? 'Markets' : 'Closed') : 'Markets'}
            <RefreshCw
              size={10}
              className={clsx('shrink-0 transition-opacity', refreshingMarket ? 'animate-spin opacity-100' : 'opacity-30')}
            />
          </button>

          <AnimatePresence>
          {showMarketPopup && (
            <motion.div
              variants={popIn}
              initial="hidden"
              animate="show"
              exit="exit"
              style={{ transformOrigin: 'top right' }}
              className="absolute right-0 top-full mt-2 z-50 w-80 bg-zinc-950 border border-zinc-700 rounded-xl p-4 shadow-2xl"
            >
              <div className="flex items-center justify-between mb-3">
                <p className="flex items-center gap-1.5 text-[10px] font-semibold tracking-widest text-zinc-400">
                  MARKET HOURS <InfoTip k="market_status" />
                </p>
              </div>

              <div className="flex items-center gap-2 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 mb-3">
                <StatusDot open={marketOpen} />
                <span className="text-sm font-medium text-zinc-200">NYSE / NASDAQ</span>
                <span className={clsx('ml-auto text-xs font-mono', marketOpen ? 'text-emerald-400' : 'text-red-400')}>
                  {marketOpen === null ? '—' : marketOpen ? 'Open' : 'Closed'}
                </span>
              </div>
              <div className="space-y-2 mb-4">
                {US_SESSIONS.map(({ label, color, start, end }) => (
                  <div key={label} className="flex items-center justify-between text-xs font-mono">
                    <span className={clsx('text-[10px] font-semibold tracking-widest', color)}>{label.toUpperCase()}</span>
                    <span className="text-zinc-400">{start} – {end} ET <span className="text-zinc-600">({etToLocalHHMM(start)} – {etToLocalHHMM(end)} {tz})</span></span>
                  </div>
                ))}
              </div>

              <div className="flex items-center gap-2 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 mb-3">
                <StatusDot open={marketOpenIN} />
                <span className="text-sm font-medium text-zinc-200">NSE / BSE</span>
                <span className={clsx('ml-auto text-xs font-mono', marketOpenIN ? 'text-emerald-400' : 'text-red-400')}>
                  {marketOpenIN === null ? '—' : marketOpenIN ? 'Open' : 'Closed'}
                </span>
              </div>
              <div className="space-y-2">
                {IN_SESSIONS.map(({ label, color, start, end }) => (
                  <div key={label} className="flex items-center justify-between text-xs font-mono">
                    <span className={clsx('text-[10px] font-semibold tracking-widest', color)}>{label.toUpperCase()}</span>
                    <span className="text-zinc-400">{start} – {end} IST <span className="text-zinc-600">({istToLocalHHMM(start)} – {istToLocalHHMM(end)} {tz})</span></span>
                  </div>
                ))}
              </div>

              <p className="mt-3 pt-3 border-t border-zinc-800 text-[10px] text-zinc-600">Auto-refreshes every {formatInterval(MARKET_STATUS_REFRESH_MS)}</p>
            </motion.div>
          )}
          </AnimatePresence>
        </div>

        {/* Account */}
        {user ? (
            <div className="relative" ref={userRef}>
              <button
                onClick={() => setShowUser(s => !s)}
                aria-label="Account menu"
                className="flex items-center justify-center w-8 h-8 rounded-full bg-indigo-500/15 border border-indigo-500/30 text-indigo-300 text-xs font-semibold uppercase transition-colors hover:border-indigo-400"
              >
                {(user.email ?? '?').slice(0, 1)}
              </button>
              <AnimatePresence>
              {showUser && (
                <motion.div
                  variants={popIn}
                  initial="hidden"
                  animate="show"
                  exit="exit"
                  style={{ transformOrigin: 'top right' }}
                  className="absolute right-0 top-full mt-2 z-50 w-72 bg-zinc-950 border border-zinc-700 rounded-xl p-2 shadow-2xl"
                >
                  {/* Account summary */}
                  <div className="flex items-center gap-3 px-3 py-3 border-b border-zinc-800 mb-1">
                    <span className="flex items-center justify-center w-9 h-9 rounded-full bg-indigo-500/15 border border-indigo-500/30 text-indigo-300 text-sm font-semibold uppercase shrink-0">
                      {(user.email ?? '?').slice(0, 1)}
                    </span>
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-zinc-200 truncate">{user.email}</p>
                      <p className="text-[10px] text-zinc-500 mt-0.5">
                        {localAuthMode ? 'Local account · this deployment only' : 'Stakeout account · synced across devices'}
                      </p>
                    </div>
                  </div>
                  <div className="px-3 py-2 border-b border-zinc-800 mb-1 space-y-1">
                    <p className="text-[10px] text-zinc-600 leading-relaxed">
                      Your watchlist and both portfolios (US &amp; India) are saved to this account.
                    </p>
                  </div>
                  <button
                    onClick={() => { setShowUser(false); navigate('/settings') }}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-zinc-300 hover:bg-zinc-900 transition-colors"
                  >
                    <Settings size={12} /> Account settings
                  </button>
                  <button
                    onClick={() => { signOut(); setShowUser(false) }}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-zinc-300 hover:bg-zinc-900 transition-colors"
                  >
                    <LogOut size={12} /> Sign out
                  </button>
                </motion.div>
              )}
              </AnimatePresence>
            </div>
          ) : isGuest ? (
            <button
              onClick={() => setShowAuthModal(true)}
              title="Browsing as a guest — nothing is saved to an account"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 text-xs font-medium transition-colors"
            >
              <UserRound size={13} />
              Guest · Sign in
            </button>
          ) : (
            <button
              onClick={() => setShowAuthModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors"
            >
              <UserRound size={13} />
              Sign in
            </button>
          )}

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

      <AnimatePresence>
        {showAuthModal && <AuthModal onClose={() => setShowAuthModal(false)} />}
      </AnimatePresence>
    </header>
  )
}
