import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import clsx from 'clsx'
import {
  AlertTriangle, Database, FileDown, Globe2, LogOut, Moon, Palette, RefreshCw,
  Settings as SettingsIcon, ShieldAlert, Sparkles, Sun, Trash2, UserRound,
} from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useAuth } from '../contexts/AuthContext'
import { usePrefs, type MarketFilter } from '../contexts/PrefsContext'
import { useTheme } from '../contexts/ThemeContext'
import { deleteAccount, downloadPortfolio } from '../api'
import { InfoTip } from './InfoTip'
import { collapse, layoutSpring } from '../lib/motion'

// NOTE: draft settings page — sections and copy are a first pass; the exact
// set of settings will be specified later. Keep each setting self-contained
// so adding/removing items stays cheap.

function Section({
  icon: Icon, title, subtitle, children,
}: {
  icon: React.ElementType
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <div className="flex items-center gap-2.5 mb-4">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
          <Icon size={15} className="text-indigo-400" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">{title}</h2>
          {subtitle && <p className="text-[11px] text-zinc-500">{subtitle}</p>}
        </div>
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  )
}

function Toggle({
  checked, onChange, label, disabled,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  disabled?: boolean
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={clsx(
        'relative w-9 h-5 rounded-full transition-colors shrink-0',
        checked ? 'bg-indigo-600' : 'bg-zinc-700',
        disabled && 'opacity-40 cursor-not-allowed',
      )}
    >
      <motion.span
        layout
        transition={layoutSpring}
        className={clsx(
          'absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white',
          checked && 'translate-x-4',
        )}
      />
    </button>
  )
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-6">
      <div className="min-w-0">
        <p className="text-xs font-medium text-zinc-300">{label}</p>
        {hint && <p className="text-[11px] text-zinc-500 mt-0.5 leading-relaxed">{hint}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  )
}

export function SettingsPage() {
  const { user, isGuest, localAuthMode, signOut } = useAuth()
  const { market, setMarket, aiEnabled, setAiEnabled, aiAvailable } = usePrefs()
  const { isDark, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const [downloading, setDownloading] = useState<'US' | 'IN' | null>(null)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const accountType = isGuest
    ? 'Guest session'
    : localAuthMode
      ? 'Local account (this deployment only)'
      : 'Stakeout account (Google / email via Supabase)'

  async function exportPortfolio(m: 'US' | 'IN') {
    setDownloading(m)
    try { await downloadPortfolio(m) } catch {}
    setDownloading(null)
  }

  async function confirmDeleteAccount() {
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteAccount()
      await signOut().catch(() => {})
      navigate('/')
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : 'Failed to delete account')
      setDeleting(false)
    }
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto flex flex-col gap-5">

        <div className="flex items-center gap-2.5">
          <SettingsIcon size={18} className="text-zinc-400" />
          <div>
            <h1 className="font-display text-lg font-bold tracking-tight text-zinc-100">Account settings</h1>
            <p className="text-xs text-zinc-500 mt-0.5">Manage your account, preferences, and data</p>
          </div>
        </div>

        {/* ── Account ──────────────────────────────────────────────────── */}
        <Section icon={UserRound} title="Account" subtitle="Who you're signed in as">
          <Row label="Email" hint={isGuest ? 'Guests have no email — sign in to sync your data across devices.' : undefined}>
            <span className="font-mono text-xs text-zinc-300">{user?.email ?? '—'}</span>
          </Row>
          <Row label="Account type">
            <span className="text-xs text-zinc-400">{accountType}</span>
          </Row>
          <Row
            label="Sign out"
            hint="Ends your session on this device. Your watchlist and portfolios stay safely in your account."
          >
            <button
              onClick={() => signOut()}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 text-zinc-300 text-xs font-medium transition-colors"
            >
              <LogOut size={12} />
              Sign out
            </button>
          </Row>
        </Section>

        {/* ── Appearance ───────────────────────────────────────────────── */}
        <Section icon={Palette} title="Appearance" subtitle="How Stakeout looks on this device">
          <Row label="Theme" hint="Terminal-dark or paper-ledger light. Saved per device.">
            <button
              onClick={(e) => {
                const rect = e.currentTarget.getBoundingClientRect()
                toggleTheme(rect.left + rect.width / 2, rect.top + rect.height / 2)
              }}
              className="theme-toggle-btn flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 text-zinc-300 text-xs font-medium transition-colors"
            >
              {isDark ? <Sun size={12} /> : <Moon size={12} />}
              Switch to {isDark ? 'light' : 'dark'} mode
            </button>
          </Row>
        </Section>

        {/* ── Preferences ──────────────────────────────────────────────── */}
        <Section icon={Globe2} title="Markets" subtitle="Defaults for watchlist and portfolio views">
          <Row
            label="Default market filter"
            hint="Which market the watchlist filter and portfolio tab open to. 'All' keeps your last-used tab."
          >
            <div className="flex rounded-lg overflow-hidden border border-zinc-800">
              {(['ALL', 'US', 'IN'] as MarketFilter[]).map(m => (
                <button
                  key={m}
                  onClick={() => setMarket(m)}
                  className={clsx(
                    'px-3 py-1.5 text-xs font-medium transition-colors',
                    market === m
                      ? 'bg-indigo-600 text-white'
                      : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200',
                  )}
                >
                  {m === 'ALL' ? 'All' : m === 'US' ? 'US' : 'India'}
                </button>
              ))}
            </div>
          </Row>
        </Section>

        {/* ── AI features ──────────────────────────────────────────────── */}
        <Section icon={Sparkles} title="AI features" subtitle="The AI Insight card and the floating AI chat">
          <Row
            label="Enable AI features"
            hint={
              aiAvailable
                ? "Turns the AI Insight card and the floating chat button off everywhere in the app. Generated by a local Ollama model on your machine — nothing about your stocks or portfolio is sent to Stakeout's servers."
                : "Local developer use only. AI features call an Ollama model running next to the backend on your own machine, so they only work when you're running Stakeout locally for development — not on this hosted deployment."
            }
          >
            <Toggle checked={aiEnabled} onChange={setAiEnabled} label="Enable AI features" disabled={!aiAvailable} />
          </Row>
        </Section>

        {/* ── Data ─────────────────────────────────────────────────────── */}
        <Section icon={Database} title="Your data" subtitle="Export or review what Stakeout stores for you">
          <Row
            label="Export portfolios"
            hint="Download each market's portfolio — holdings, transactions, and P&L — as an Excel workbook."
          >
            <div className="flex items-center gap-2">
              {(['US', 'IN'] as const).map(m => (
                <button
                  key={m}
                  onClick={() => exportPortfolio(m)}
                  disabled={downloading !== null}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/20 transition-colors disabled:opacity-40"
                >
                  {downloading === m ? <RefreshCw size={11} className="animate-spin" /> : <FileDown size={11} />}
                  {m === 'US' ? 'US' : 'India'}
                </button>
              ))}
            </div>
          </Row>
          <Row label={'What\u2019s stored'} hint="Your watchlist tickers, portfolio transactions, and account email. Market prices and news are public data, cached server-side, and not tied to you.">
            <InfoTip k="portfolio_value" />
          </Row>
        </Section>

        {/* ── Danger zone ──────────────────────────────────────────────── */}
        <div className="bg-zinc-900 border border-red-500/20 rounded-xl p-5">
          <div className="flex items-center gap-2.5 mb-4">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-red-500/10 border border-red-500/20">
              <ShieldAlert size={15} className="text-red-400" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-zinc-100">Danger zone</h2>
              <p className="text-[11px] text-zinc-500">Irreversible actions</p>
            </div>
          </div>
          <Row
            label="Delete account"
            hint={
              isGuest
                ? "You're browsing as a guest — there's no account to delete. Your session data just lives in this browser."
                : 'Permanently removes your account, watchlist, and portfolios. This cannot be undone.'
            }
          >
            {!confirmingDelete && (
              <button
                disabled={isGuest}
                onClick={() => setConfirmingDelete(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
              >
                <Trash2 size={12} />
                Delete account
              </button>
            )}
          </Row>

          <AnimatePresence>
            {confirmingDelete && (
              <motion.div
                variants={collapse}
                initial="hidden"
                animate="show"
                exit="exit"
                style={{ overflow: 'hidden' }}
                className="mt-4"
              >
                <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3.5">
                  <div className="flex items-start gap-2">
                    <AlertTriangle size={14} className="text-red-400 shrink-0 mt-0.5" />
                    <p className="text-xs text-red-300 leading-relaxed">
                      This permanently deletes your account, watchlist, and portfolios — including on the
                      auth provider. There is no undo.
                    </p>
                  </div>
                  {deleteError && <p className="text-[11px] text-red-400 mt-2">{deleteError}</p>}
                  <div className="flex items-center gap-2 mt-3">
                    <button
                      onClick={confirmDeleteAccount}
                      disabled={deleting}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs font-medium transition-colors disabled:opacity-50"
                    >
                      {deleting ? <RefreshCw size={12} className="animate-spin" /> : <Trash2 size={12} />}
                      Yes, permanently delete my account
                    </button>
                    <button
                      onClick={() => { setConfirmingDelete(false); setDeleteError(null) }}
                      disabled={deleting}
                      className="px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 text-zinc-300 text-xs font-medium transition-colors disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <p className="text-center text-[11px] text-zinc-600 pb-4">
          More settings (display currency, notifications, refresh intervals) are on the roadmap.
        </p>
      </div>
    </div>
  )
}
