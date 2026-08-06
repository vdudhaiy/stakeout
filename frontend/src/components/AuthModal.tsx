import { useState } from 'react'
import clsx from 'clsx'
import { Mail, Lock, RefreshCw, X } from 'lucide-react'
import { motion } from 'motion/react'
import { useAuth } from '../contexts/AuthContext'
import { overlayFade, scaleIn } from '../lib/motion'

interface Props {
  onClose: () => void
}

interface PasswordFieldsProps {
  mode: 'signin' | 'signup'
  setMode: (m: 'signin' | 'signup') => void
  email: string
  onEmailChange: (v: string) => void
  password: string
  onPasswordChange: (v: string) => void
  onSubmit: () => void
  sending: boolean
  error: string | null
  /** Shown as "Create a password (…)" on signup. Omit when there's no fixed
   * policy to state up front (e.g. Supabase mode, where the real policy
   * lives in that project's dashboard and any violation is reported by the
   * signup call itself, not guessed at here). */
  passwordHint?: string
  /** "Forgot password?" link under the field, signin only. Omit for local
   * mode — there's no email-based recovery for local accounts. */
  onForgotPassword?: () => void
}

/** Shared Log In / Sign Up email+password form — used for both local-auth
 * mode and Supabase's password option, which differ only in where the
 * submit handler sends the credentials. */
function PasswordFields({
  mode, setMode, email, onEmailChange, password, onPasswordChange, onSubmit, sending, error, passwordHint, onForgotPassword,
}: PasswordFieldsProps) {
  return (
    <>
      <div className="flex rounded-lg border border-zinc-700 overflow-hidden mb-4 text-xs font-medium">
        <button
          onClick={() => setMode('signin')}
          className={clsx('flex-1 py-2 transition-colors', mode === 'signin' ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300')}
        >
          Log In
        </button>
        <button
          onClick={() => setMode('signup')}
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
          onChange={e => onEmailChange(e.target.value)}
          className="w-full bg-zinc-950 text-zinc-200 text-sm rounded-lg px-3 py-2.5 outline-none border border-zinc-700 focus:border-indigo-500 transition-colors placeholder-zinc-600"
        />
        <input
          type="password"
          placeholder={mode === 'signup' ? (passwordHint ? `Create a password (${passwordHint})` : 'Create a password') : 'Password'}
          value={password}
          onChange={e => onPasswordChange(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && onSubmit()}
          className="w-full bg-zinc-950 text-zinc-200 text-sm rounded-lg px-3 py-2.5 outline-none border border-zinc-700 focus:border-indigo-500 transition-colors placeholder-zinc-600"
        />
        {mode === 'signin' && onForgotPassword && (
          <div className="text-right">
            <button
              onClick={onForgotPassword}
              className="text-[0.6875rem] text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              Forgot password?
            </button>
          </div>
        )}
        <button
          onClick={onSubmit}
          disabled={sending}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
        >
          {sending ? <RefreshCw size={13} className="animate-spin" /> : <Lock size={13} />}
          {mode === 'signup' ? 'Create Account' : 'Log In'}
        </button>
        {error && <p className="text-[0.6875rem] text-red-400">{error}</p>}
      </div>
    </>
  )
}

export function AuthModal({ onClose }: Props) {
  const {
    signInWithGoogle, signInWithEmail, signUpWithPassword, signInWithPassword, sendPasswordReset,
    localSignUp, localSignIn, continueAsGuest, isGuest, localAuthMode,
  } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  /** Supabase mode only: password is the default, magic-link is opt-in. */
  const [authMethod, setAuthMethod] = useState<'magic' | 'password'>('password')
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)
  const [confirmSent, setConfirmSent] = useState(false)
  const [forgotMode, setForgotMode] = useState(false)
  const [resetSent, setResetSent] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function handleGuest() {
    continueAsGuest()
    onClose()
  }

  function updateEmail(v: string) { setEmail(v); setError(null) }
  function updatePassword(v: string) { setPassword(v); setError(null) }

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

  async function submitCloudPassword() {
    if (!email.includes('@')) { setError('Enter a valid email address'); return }
    if (!password) { setError('Enter a password'); return }
    setSending(true)
    setError(null)
    try {
      if (mode === 'signup') {
        // Password strength is enforced by Supabase (Authentication → Providers
        // → Email), not duplicated here — a weak password comes back as a
        // normal `error` below, worded however that project is configured.
        const { needsConfirmation } = await signUpWithPassword(email, password)
        if (needsConfirmation) setConfirmSent(true)
        else onClose()
      } else {
        await signInWithPassword(email, password)
        onClose()
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
    } finally {
      setSending(false)
    }
  }

  async function submitForgotPassword() {
    if (!email.includes('@')) { setError('Enter a valid email address'); return }
    setSending(true)
    setError(null)
    try {
      await sendPasswordReset(email)
      setResetSent(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not send the reset link')
    } finally {
      setSending(false)
    }
  }

  return (
    <motion.div
      variants={overlayFade}
      initial="hidden"
      animate="show"
      exit="exit"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onMouseDown={onClose}
    >
      <motion.div
        variants={scaleIn}
        className="bg-zinc-900 border border-zinc-700 rounded-xl p-5 sm:p-6 w-full max-w-[22rem] max-h-[90dvh] overflow-y-auto shadow-2xl"
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
          <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[0.6875rem] text-amber-300">
            You're browsing as a guest — signing in starts your real account. Your guest
            session's watchlist and portfolio won't be saved.
          </div>
        )}

        {localAuthMode ? (
          <PasswordFields
            mode={mode}
            setMode={m => { setMode(m); setError(null) }}
            email={email}
            onEmailChange={updateEmail}
            password={password}
            onPasswordChange={updatePassword}
            onSubmit={submitLocal}
            sending={sending}
            error={error}
            passwordHint="min. 8 characters"
          />
        ) : sent ? (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-400">
            Check your inbox — a sign-in link is on its way to <span className="font-mono">{email}</span>.
          </div>
        ) : confirmSent ? (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-400">
            Almost there — confirm <span className="font-mono">{email}</span> using the link we just
            emailed you, then log in.
          </div>
        ) : resetSent ? (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-400">
            Check your inbox — a password reset link is on its way to <span className="font-mono">{email}</span>.
          </div>
        ) : forgotMode ? (
          <>
            <p className="text-xs text-zinc-500 mb-3">
              Enter your email and we'll send you a link to reset your password.
            </p>
            <div className="space-y-2">
              <input
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={e => updateEmail(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && submitForgotPassword()}
                autoFocus
                className="w-full bg-zinc-950 text-zinc-200 text-sm rounded-lg px-3 py-2.5 outline-none border border-zinc-700 focus:border-indigo-500 transition-colors placeholder-zinc-600"
              />
              <button
                onClick={submitForgotPassword}
                disabled={sending}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
              >
                {sending ? <RefreshCw size={13} className="animate-spin" /> : <Mail size={13} />}
                Send reset link
              </button>
              {error && <p className="text-[0.6875rem] text-red-400">{error}</p>}
            </div>
            <div className="mt-3 text-center">
              <button
                onClick={() => { setForgotMode(false); setError(null) }}
                className="text-[0.6875rem] text-zinc-500 hover:text-zinc-300 transition-colors underline underline-offset-2"
              >
                Back to log in
              </button>
            </div>
          </>
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
              <span className="text-[0.625rem] text-zinc-600 tracking-widest">OR</span>
              <div className="flex-1 h-px bg-zinc-800" />
            </div>

            {authMethod === 'magic' ? (
              <div className="space-y-2">
                <input
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={e => updateEmail(e.target.value)}
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
                {error && <p className="text-[0.6875rem] text-red-400">{error}</p>}
              </div>
            ) : (
              <PasswordFields
                mode={mode}
                setMode={m => { setMode(m); setError(null) }}
                email={email}
                onEmailChange={updateEmail}
                password={password}
                onPasswordChange={updatePassword}
                onSubmit={submitCloudPassword}
                sending={sending}
                error={error}
                onForgotPassword={() => { setForgotMode(true); setError(null) }}
              />
            )}

            <div className="mt-3 text-center">
              <button
                onClick={() => { setAuthMethod(m => m === 'magic' ? 'password' : 'magic'); setError(null) }}
                className="text-[0.6875rem] text-zinc-500 hover:text-zinc-300 transition-colors underline underline-offset-2"
              >
                {authMethod === 'magic' ? 'Use a password instead' : 'Use a magic link instead'}
              </button>
            </div>
          </>
        )}

        {!isGuest && !sent && !confirmSent && !resetSent && !forgotMode && (
          <div className="mt-4 text-center">
            <button
              onClick={handleGuest}
              className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              Continue as Guest
            </button>
            <p className="text-[0.625rem] text-zinc-700 mt-1">
              Nothing saved to an account — local to this device for this browser session.
            </p>
          </div>
        )}
      </motion.div>
    </motion.div>
  )
}
