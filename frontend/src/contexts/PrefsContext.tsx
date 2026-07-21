import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export type MarketFilter = 'ALL' | 'US' | 'IN'

interface PrefsContextType {
  market: MarketFilter
  setMarket: (m: MarketFilter) => void
}

const PrefsContext = createContext<PrefsContextType>({
  market: 'ALL',
  setMarket: () => {},
})

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [market, setMarket] = useState<MarketFilter>(
    () => (localStorage.getItem('stakeout-market') as MarketFilter) || 'ALL',
  )

  useEffect(() => { localStorage.setItem('stakeout-market', market) }, [market])

  return (
    <PrefsContext.Provider value={{ market, setMarket }}>
      {children}
    </PrefsContext.Provider>
  )
}

export const usePrefs = () => useContext(PrefsContext)
