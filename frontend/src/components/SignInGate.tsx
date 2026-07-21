import { useState } from 'react'
import { LayoutDashboard, Briefcase, UserRound } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { AuthModal } from './AuthModal'

interface Props {
  view: 'dashboard' | 'portfolio'
}

const COPY = {
  dashboard: { icon: LayoutDashboard, label: 'Dashboard' },
  portfolio: { icon: Briefcase, label: 'Portfolio' },
} as const

/** Shown in place of the Dashboard/Portfolio view when nobody's signed in
 * and the visitor hasn't chosen to continue as a guest yet. */
export function SignInGate({ view }: Props) {
  const { continueAsGuest } = useAuth()
  const [showAuthModal, setShowAuthModal] = useState(false)
  const { icon: Icon, label } = COPY[view]

  return (
    <div className="flex flex-1 items-center justify-center">
      <div className="flex flex-col items-center text-center max-w-sm px-6">
        <div className="w-14 h-14 rounded-2xl bg-zinc-800 border border-zinc-700 flex items-center justify-center mb-5">
          <Icon size={24} className="text-zinc-500" />
        </div>
        <h2 className="text-base font-semibold text-zinc-100 mb-1.5">Sign in to view your {label}</h2>
        <p className="text-xs text-zinc-500 leading-relaxed mb-6">
          Your watchlist and portfolio are tied to your account. Sign in to see them here,
          or continue as a guest to try Stakeout without an account — nothing you do will
          be saved past this browser session.
        </p>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAuthModal(true)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors"
          >
            <UserRound size={14} />
            Sign In
          </button>
          <button
            onClick={continueAsGuest}
            className="px-4 py-2 rounded-lg border border-zinc-700 hover:border-zinc-600 text-zinc-300 text-sm font-medium transition-colors"
          >
            Continue as Guest
          </button>
        </div>
      </div>

      {showAuthModal && <AuthModal onClose={() => setShowAuthModal(false)} />}
    </div>
  )
}
