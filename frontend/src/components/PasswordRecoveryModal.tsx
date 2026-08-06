import { useState } from 'react'
import { CheckCircle2, Lock, RefreshCw, X } from 'lucide-react'
import { motion } from 'motion/react'
import { useAuth } from '../contexts/AuthContext'
import { overlayFade, scaleIn } from '../lib/motion'

/** Shown automatically when the visitor lands here via a Supabase
 * password-reset email link — driven by AuthContext's `passwordRecovery`
 * flag rather than opened like AuthModal, since the link can land on any
 * page with no modal already open. */
export function PasswordRecoveryModal() {
  const { updatePassword, dismissPasswordRecovery } = useAuth()
  const [password, setPassword] = useState('')
  const [sending, setSending] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    if (!password) { setError('Enter a new password'); return }
    setSending(true)
    setError(null)
    try {
      await updatePassword(password)
      setDone(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
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
    >
      <motion.div
        variants={scaleIn}
        className="bg-zinc-900 border border-zinc-700 rounded-xl p-5 sm:p-6 w-full max-w-[22rem] shadow-2xl"
      >
        {done ? (
          <>
            <div className="flex items-center gap-2 mb-1">
              <CheckCircle2 size={16} className="text-emerald-400" />
              <h2 className="font-display text-lg font-semibold text-zinc-100">Password updated</h2>
            </div>
            <p className="text-xs text-zinc-500 mb-5">You're signed in with your new password.</p>
            <button
              onClick={dismissPasswordRecovery}
              className="w-full px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors"
            >
              Done
            </button>
          </>
        ) : (
          <>
            <div className="flex items-start justify-between mb-1">
              <h2 className="font-display text-lg font-semibold text-zinc-100">Set a new password</h2>
              <button onClick={dismissPasswordRecovery} aria-label="Close" className="text-zinc-500 hover:text-zinc-300 transition-colors">
                <X size={16} />
              </button>
            </div>
            <p className="text-xs text-zinc-500 mb-5">
              You followed a password reset link. Choose a new password to finish signing in.
            </p>
            <div className="space-y-2">
              <input
                type="password"
                placeholder="New password"
                value={password}
                onChange={e => { setPassword(e.target.value); setError(null) }}
                onKeyDown={e => e.key === 'Enter' && submit()}
                autoFocus
                className="w-full bg-zinc-950 text-zinc-200 text-sm rounded-lg px-3 py-2.5 outline-none border border-zinc-700 focus:border-indigo-500 transition-colors placeholder-zinc-600"
              />
              <button
                onClick={submit}
                disabled={sending}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
              >
                {sending ? <RefreshCw size={13} className="animate-spin" /> : <Lock size={13} />}
                Update Password
              </button>
              {error && <p className="text-[0.6875rem] text-red-400">{error}</p>}
            </div>
          </>
        )}
      </motion.div>
    </motion.div>
  )
}
