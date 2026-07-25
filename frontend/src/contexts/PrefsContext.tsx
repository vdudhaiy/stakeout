import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { IS_LOCAL_DEV } from '../utils/env'

export type MarketFilter = 'ALL' | 'US' | 'IN'

interface PrefsContextType {
  market: MarketFilter
  setMarket: (m: MarketFilter) => void
  /** Master switch for the AI Insight card + floating AI chat, set on the Settings page. Always false when !aiAvailable. */
  aiEnabled: boolean
  setAiEnabled: (v: boolean) => void
  /** Whether AI features can be turned on at all — false on a deployed (cloud) instance, since they call an Ollama instance expected to run next to the backend. */
  aiAvailable: boolean
}

const PrefsContext = createContext<PrefsContextType>({
  market: 'ALL',
  setMarket: () => {},
  aiEnabled: false,
  setAiEnabled: () => {},
  aiAvailable: IS_LOCAL_DEV,
})

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [market, setMarket] = useState<MarketFilter>(
    () => (localStorage.getItem('stakeout-market') as MarketFilter) || 'ALL',
  )
  const [aiEnabledPref, setAiEnabledPref] = useState<boolean>(
    () => localStorage.getItem('stakeout-ai-enabled') === 'true', // default off — opt-in, since it needs a local Ollama model running
  )

  useEffect(() => { localStorage.setItem('stakeout-market', market) }, [market])
  useEffect(() => { localStorage.setItem('stakeout-ai-enabled', String(aiEnabledPref)) }, [aiEnabledPref])

  // Cloud deployments have no Ollama instance to call — the stored
  // preference is ignored (and can't be set) outside local dev, rather than
  // trusting a stale 'true' left over from before a build was deployed.
  const aiEnabled = IS_LOCAL_DEV && aiEnabledPref

  return (
    <PrefsContext.Provider value={{ market, setMarket, aiEnabled, setAiEnabled: setAiEnabledPref, aiAvailable: IS_LOCAL_DEV }}>
      {children}
    </PrefsContext.Provider>
  )
}

export const usePrefs = () => useContext(PrefsContext)
