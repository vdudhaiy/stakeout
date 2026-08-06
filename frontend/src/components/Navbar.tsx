import { useState, useRef, useEffect } from 'react'
import clsx from 'clsx'
import { House, LineChart, Briefcase, Sun, Moon, RefreshCw, LogOut, UserRound, Settings, Compass, Menu, X } from 'lucide-react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
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

/** The Stakeout wordmark: a candle-wick spark over the name. The tagline is
 *  dropped on phones, where the row has to fit the menu, markets and account
 *  controls too. */
function Wordmark() {
  return (
    <NavLink to="/" className="tap-target flex items-center gap-2 sm:gap-2.5 group min-w-0">
      <svg width="20" height="20" viewBox="0 0 32 32" aria-hidden="true" className="shrink-0">
        <rect width="32" height="32" rx="7" className="fill-zinc-800 group-hover:fill-zinc-700 transition-colors" />
        <path d="M9 21l4-6 3 3 5-8" stroke="#E4B95B" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <circle cx="21" cy="10" r="2" fill="#E4B95B" />
      </svg>
      <span className="flex flex-col leading-none min-w-0">
        <span className="font-display text-zinc-100 font-semibold tracking-tight text-[0.9375rem]">Stakeout</span>
        <span className="hidden sm:block text-[0.53125rem] tracking-[0.18em] text-zinc-600 uppercase mt-0.5">Open markets, open source</span>
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
  const location = useLocation()
  const [showMarketPopup, setShowMarketPopup] = useState(false)
  const [showUser, setShowUser] = useState(false)
  const [showAuthModal, setShowAuthModal] = useState(false)
  const [showMobileNav, setShowMobileNav] = useState(false)
  const [refreshingMarket, setRefreshingMarket] = useState(false)
  const marketRef = useRef<HTMLDivElement>(null)
  const userRef = useRef<HTMLDivElement>(null)
  const tz = localTzAbbr()

  // Navigating away is the natural "done" for the mobile menu — without this
  // it stays open over the page the user just asked for.
  useEffect(() => { setShowMobileNav(false) }, [location.pathname])

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
    <header className="relative flex items-center h-14 px-3 sm:px-6 border-b border-zinc-800 bg-zinc-950 shrink-0 gap-3 lg:gap-8">
      {/* Menu toggle — the four nav links don't fit alongside the wordmark and
          the account controls until there's tablet-width room for them. */}
      <button
        onClick={() => setShowMobileNav(o => !o)}
        aria-label={showMobileNav ? 'Close navigation menu' : 'Open navigation menu'}
        aria-expanded={showMobileNav}
        className="tap-target lg:hidden flex items-center justify-center w-9 h-9 -ml-1 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 transition-colors shrink-0"
      >
        {showMobileNav ? <X size={18} /> : <Menu size={18} />}
      </button>

      <Wordmark />

      <nav className="hidden lg:flex items-center gap-1">
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

      {/* Slide-down menu for the links hidden above */}
      <AnimatePresence>
        {showMobileNav && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              onClick={() => setShowMobileNav(false)}
              className="lg:hidden fixed inset-0 top-14 z-40 bg-black/50"
            />
            <motion.nav
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
              className="lg:hidden absolute inset-x-0 top-full z-40 flex flex-col gap-1 border-b border-zinc-800 bg-zinc-950 p-3 shadow-2xl"
            >
              {NAV_ITEMS.map(({ path, label, icon: Icon, end }) => (
                <NavLink
                  key={path}
                  to={path}
                  end={end}
                  className={({ isActive }) => clsx(
                    'flex items-center gap-3 px-3 py-3 rounded-lg text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-zinc-800 text-zinc-100'
                      : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900',
                  )}
                >
                  <Icon size={16} />
                  {label}
                </NavLink>
              ))}
            </motion.nav>
          </>
        )}
      </AnimatePresence>

      <div className="ml-auto flex items-center gap-1.5 sm:gap-3">

        {/* Markets status (US + India) */}
        <div className="relative" ref={marketRef}>
          <button
            onClick={handleMarketClick}
            aria-label="Market hours"
            className={clsx(
              'tap-target flex items-center gap-1.5 sm:gap-2 px-2 sm:px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-colors',
              showMarketPopup
                ? 'border-zinc-700 bg-zinc-900 text-zinc-300'
                : 'border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:bg-zinc-900 hover:text-zinc-300',
            )}
          >
            <span className="flex items-center gap-1">
              <StatusDot open={marketOpen} />
              <span className="font-mono text-[0.625rem] text-zinc-500">US</span>
            </span>
            <span className="flex items-center gap-1">
              <StatusDot open={marketOpenIN} />
              <span className="font-mono text-[0.625rem] text-zinc-500">IN</span>
            </span>
            {/* The word is the first thing to go when space is tight — the two
                status dots already carry the meaning. */}
            <span className="hidden sm:inline">
              {bothKnown ? (anyOpen ? 'Markets' : 'Closed') : 'Markets'}
            </span>
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
              className="absolute right-0 top-full mt-2 z-50 w-[min(20rem,calc(100vw-1.5rem))] bg-zinc-950 border border-zinc-700 rounded-xl p-4 shadow-2xl"
            >
              <div className="flex items-center justify-between mb-3">
                <p className="flex items-center gap-1.5 text-[0.625rem] font-semibold tracking-widest text-zinc-400">
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
                  <div key={label} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-0.5 text-xs font-mono">
                    <span className={clsx('text-[0.625rem] font-semibold tracking-widest', color)}>{label.toUpperCase()}</span>
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
                  <div key={label} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-0.5 text-xs font-mono">
                    <span className={clsx('text-[0.625rem] font-semibold tracking-widest', color)}>{label.toUpperCase()}</span>
                    <span className="text-zinc-400">{start} – {end} IST <span className="text-zinc-600">({istToLocalHHMM(start)} – {istToLocalHHMM(end)} {tz})</span></span>
                  </div>
                ))}
              </div>

              <p className="mt-3 pt-3 border-t border-zinc-800 text-[0.625rem] text-zinc-600">Auto-refreshes every {formatInterval(MARKET_STATUS_REFRESH_MS)}</p>
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
                className="tap-target flex items-center justify-center w-8 h-8 rounded-full bg-indigo-500/15 border border-indigo-500/30 text-indigo-300 text-xs font-semibold uppercase transition-colors hover:border-indigo-400"
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
                  className="absolute right-0 top-full mt-2 z-50 w-[min(18rem,calc(100vw-1.5rem))] bg-zinc-950 border border-zinc-700 rounded-xl p-2 shadow-2xl"
                >
                  {/* Account summary */}
                  <div className="flex items-center gap-3 px-3 py-3 border-b border-zinc-800 mb-1">
                    <span className="flex items-center justify-center w-9 h-9 rounded-full bg-indigo-500/15 border border-indigo-500/30 text-indigo-300 text-sm font-semibold uppercase shrink-0">
                      {(user.email ?? '?').slice(0, 1)}
                    </span>
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-zinc-200 truncate">{user.email}</p>
                      <p className="text-[0.625rem] text-zinc-500 mt-0.5">
                        {localAuthMode ? 'Local account · this deployment only' : 'Stakeout account · synced across devices'}
                      </p>
                    </div>
                  </div>
                  <div className="px-3 py-2 border-b border-zinc-800 mb-1 space-y-1">
                    <p className="text-[0.625rem] text-zinc-600 leading-relaxed">
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
              className="tap-target flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 text-xs font-medium transition-colors whitespace-nowrap"
            >
              <UserRound size={13} />
              <span className="hidden sm:inline">Guest · </span>Sign in
            </button>
          ) : (
            <button
              onClick={() => setShowAuthModal(true)}
              className="tap-target flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors whitespace-nowrap"
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
          aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          className="theme-toggle-btn tap-target flex items-center justify-center w-8 h-8 rounded-lg text-zinc-400 shrink-0"
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
