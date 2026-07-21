import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase, authEnabled } from '../lib/supabase'
import { localSignUp, localSignIn, localSignOut } from '../lib/localAuth'
import { setAuthTokenGetter } from '../api'
import { isGuestModeActive, setGuestModeActive } from '../lib/guestMode'
import { clearGuestPortfolio } from '../lib/guestPortfolio'
import { clearGuestWatchlist } from '../lib/guestWatchlist'

const LOCAL_TOKEN_KEY = 'stakeout-local-auth-token'
const LOCAL_EMAIL_KEY = 'stakeout-local-auth-email'

/** Frontend mirrors the backend's own automatic switch: no Supabase project
 * configured means the backend runs its own local email/password auth. */
const localAuthMode = !authEnabled

export interface AuthUser {
  email: string | null
}

interface AuthContextType {
  /** Whether Supabase is configured for this deployment */
  enabled: boolean
  /** True when there's no Supabase project — sign-in uses local email/password accounts instead */
  localAuthMode: boolean
  user: AuthUser | null
  loading: boolean
  /** True once the visitor has chosen "Continue as Guest" this session */
  isGuest: boolean
  /** True when the dashboard/portfolio may be viewed: signed in, or guest */
  canUseApp: boolean
  continueAsGuest: () => void
  signInWithGoogle: () => Promise<void>
  signInWithEmail: (email: string) => Promise<void>
  localSignUp: (email: string, password: string) => Promise<void>
  localSignIn: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextType>({
  enabled: false,
  localAuthMode: false,
  user: null,
  loading: false,
  isGuest: false,
  canUseApp: true,
  continueAsGuest: () => {},
  signInWithGoogle: async () => {},
  signInWithEmail: async () => {},
  localSignUp: async () => {},
  localSignIn: async () => {},
  signOut: async () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(authEnabled)
  const [isGuest, setIsGuest] = useState(isGuestModeActive)
  const [localToken, setLocalToken] = useState<string | null>(
    () => (localAuthMode ? localStorage.getItem(LOCAL_TOKEN_KEY) : null),
  )
  const [localEmail, setLocalEmail] = useState<string | null>(
    () => (localAuthMode ? localStorage.getItem(LOCAL_EMAIL_KEY) : null),
  )
  const localTokenRef = useRef(localToken)
  localTokenRef.current = localToken

  useEffect(() => {
    if (!supabase) return
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })
    const { data: sub } = supabase.auth.onAuthStateChange((_event, s) => setSession(s))
    return () => sub.subscription.unsubscribe()
  }, [])

  // API layer pulls the freshest access token for its Authorization header.
  // Registered synchronously during render, not inside a useEffect: a child
  // component's own effects (e.g. a page's initial data fetch) can fire
  // before this component's effects do — child effects run before parent
  // effects on mount — so an effect-based registration can lose that race
  // on first paint and send the very first request with no token at all.
  setAuthTokenGetter(async () => {
    if (localAuthMode) return localTokenRef.current
    if (!supabase) return null
    const { data } = await supabase.auth.getSession()
    return data.session?.access_token ?? null
  })

  // A real session (Supabase or local) always wins over guest mode — once
  // one appears, guest mode ends and its local-only data is discarded (it
  // was never meant to survive past the session anyway).
  useEffect(() => {
    const signedIn = !!session?.user || !!localToken
    if (signedIn && isGuest) {
      setGuestModeActive(false)
      clearGuestPortfolio()
      clearGuestWatchlist()
      setIsGuest(false)
    }
  }, [session, localToken, isGuest])

  function continueAsGuest() {
    setGuestModeActive(true)
    setIsGuest(true)
  }

  async function signInWithGoogle() {
    if (!supabase) return
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: window.location.origin },
    })
  }

  async function signInWithEmail(email: string) {
    if (!supabase) return
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: window.location.origin },
    })
    if (error) throw error
  }

  function _storeLocalSession(token: string, email: string) {
    localStorage.setItem(LOCAL_TOKEN_KEY, token)
    localStorage.setItem(LOCAL_EMAIL_KEY, email)
    setLocalToken(token)
    setLocalEmail(email)
  }

  async function handleLocalSignUp(email: string, password: string) {
    const result = await localSignUp(email, password)
    _storeLocalSession(result.token, result.email)
  }

  async function handleLocalSignIn(email: string, password: string) {
    const result = await localSignIn(email, password)
    _storeLocalSession(result.token, result.email)
  }

  async function signOut() {
    if (localAuthMode) {
      if (localToken) await localSignOut(localToken)
      localStorage.removeItem(LOCAL_TOKEN_KEY)
      localStorage.removeItem(LOCAL_EMAIL_KEY)
      setLocalToken(null)
      setLocalEmail(null)
      return
    }
    if (!supabase) return
    await supabase.auth.signOut()
  }

  const user: AuthUser | null = localAuthMode
    ? (localEmail ? { email: localEmail } : null)
    : (session?.user ? { email: session.user.email ?? null } : null)

  const canUseApp = !!user || isGuest

  return (
    <AuthContext.Provider
      value={{
        enabled: authEnabled, localAuthMode, user, loading, isGuest, canUseApp, continueAsGuest,
        signInWithGoogle, signInWithEmail,
        localSignUp: handleLocalSignUp, localSignIn: handleLocalSignIn,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
