import { useState } from 'react'
import clsx from 'clsx'
import { Mail, Lock, RefreshCw, X } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

interface Props {
  onClose: () => void
}

export function AuthModal({ onClose }: Props) {
  const {
    signInWithGoogle, signInWithEmail, localSignUp, localSignIn,
    continueAsGuest, isGuest, localAuthMode,
  } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function handleGuest() {
    continueAsGuest()
    onClose()
  }

  async function submitEmail() {
    if (!email.includes('@')) { setError('Enter a valid email address'); return }
    setSending(true)
    setError(null)
    try {
      await signInWithEmail(email)
      setSent(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not send the sign-in link')
    } finally {
      setSending(false)
    }
  }

  async function submitLocal() {
    if (!email.includes('@')) { setError('Enter a valid email address'); return }
    if (password.length < 8) { setError('Password must be at least 8 characters'); return }
    setSending(true)
    setError(null)
    try {
      if (mode === 'signup') await localSignUp(email, password)
      else await localSignIn(email, password)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onMouseDown={onClose}>
      <div
        className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-[22rem] shadow-2xl"
        onMouseDown={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-1">
          <h2 className="font-display text-lg font-semibold text-zinc-100">Sign in to Stakeout</h2>
          <button onClick={onClose} aria-label="Close" className="text-zinc-500 hover:text-zinc-300 transition-colors">
            <X size={16} />
          </button>
        </div>
        <p className="text-xs text-zinc-500 mb-5">
          {localAuthMode
            ? 'Local account — stored in this database only, nothing leaves your machine.'
            : 'Your watchlist and portfolios sync to your account across devices.'}
        </p>

        {isGuest && (
          <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300">
            You're browsing as a guest — signing in starts your real account. Your guest
            session's watchlist and portfolio won't be saved.
          </div>
        )}

        {localAuthMode ? (
          <>
            <div className="flex rounded-lg border border-zinc-700 overflow-hidden mb-4 text-xs font-medium">
              <button
                onClick={() => { setMode('signin'); setError(null) }}
                className={clsx('flex-1 py-2 transition-colors', mode === 'signin' ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300')}
              >
                Log In
              </button>
              <button
                onClick={() => { setMode('signup'); setError(null) }}
                className={clsx('flex-1 py-2 transition-colors', mode === 'signup' ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300')}
              >
                Sign Up
              </button>
            </div>

            <div className="space-y-2">
              <input
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={e => { setEmail(e.target.value); setError(null) }}
                className="w-full bg-zinc-950 text-zinc-200 text-sm rounded-lg px-3 py-2.5 outline-none border border-zinc-700 focus:border-indigo-500 transition-colors placeholder-zinc-600"
              />
              <input
                type="password"
                placeholder={mode === 'signup' ? 'Create a password (min. 8 characters)' : 'Password'}
                value={password}
                onChange={e => { setPassword(e.target.value); setError(null) }}
                onKeyDown={e => e.key === 'Enter' && submitLocal()}
                className="w-full bg-zinc-950 text-zinc-200 text-sm rounded-lg px-3 py-2.5 outline-none border border-zinc-700 focus:border-indigo-500 transition-colors placeholder-zinc-600"
              />
              <button
                onClick={submitLocal}
                disabled={sending}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
              >
                {sending ? <RefreshCw size={13} className="animate-spin" /> : <Lock size={13} />}
                {mode === 'signup' ? 'Create Account' : 'Log In'}
              </button>
              {error && <p className="text-[11px] text-red-400">{error}</p>}
            </div>
          </>
        ) : sent ? (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-400">
            Check your inbox — a sign-in link is on its way to <span className="font-mono">{email}</span>.
          </div>
        ) : (
          <>
            <button
              onClick={signInWithGoogle}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-zinc-100 hover:bg-white text-zinc-950 text-sm font-medium transition-colors"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38z"/>
              </svg>
              Continue with Google
            </button>

            <div className="flex items-center gap-3 my-4">
              <div className="flex-1 h-px bg-zinc-800" />
              <span className="text-[10px] text-zinc-600 tracking-widest">OR</span>
              <div className="flex-1 h-px bg-zinc-800" />
            </div>

            <div className="space-y-2">
              <input
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={e => { setEmail(e.target.value); setError(null) }}
                onKeyDown={e => e.key === 'Enter' && submitEmail()}
                className="w-full bg-zinc-950 text-zinc-200 text-sm rounded-lg px-3 py-2.5 outline-none border border-zinc-700 focus:border-indigo-500 transition-colors placeholder-zinc-600"
              />
              <button
                onClick={submitEmail}
                disabled={sending}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
              >
                {sending ? <RefreshCw size={13} className="animate-spin" /> : <Mail size={13} />}
                Email me a sign-in link
              </button>
              {error && <p className="text-[11px] text-red-400">{error}</p>}
            </div>
          </>
        )}

        {!isGuest && !sent && (
          <div className="mt-4 text-center">
            <button
              onClick={handleGuest}
              className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              Continue as Guest
            </button>
            <p className="text-[10px] text-zinc-700 mt-1">
              Nothing saved to an account — local to this device for this browser session.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
