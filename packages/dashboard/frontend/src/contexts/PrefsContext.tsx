import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { Currency } from '../utils/currency'
import { fetchFxRate } from '../api'

export type MarketFilter = 'ALL' | 'US' | 'IN'

interface PrefsContextType {
  market: MarketFilter
  setMarket: (m: MarketFilter) => void
  currency: Currency
  setCurrency: (c: Currency) => void
  /** Daily USD→INR reference rate; null until first fetch resolves. */
  usdInr: number | null
  fxSource: string | null
}

const PrefsContext = createContext<PrefsContextType>({
  market: 'ALL',
  setMarket: () => {},
  currency: 'USD',
  setCurrency: () => {},
  usdInr: null,
  fxSource: null,
})

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [market, setMarket] = useState<MarketFilter>(
    () => (localStorage.getItem('stakeout-market') as MarketFilter) || 'ALL',
  )
  const [currency, setCurrency] = useState<Currency>(
    () => (localStorage.getItem('stakeout-currency') as Currency) || 'USD',
  )
  const [usdInr, setUsdInr] = useState<number | null>(null)
  const [fxSource, setFxSource] = useState<string | null>(null)

  useEffect(() => { localStorage.setItem('stakeout-market', market) }, [market])
  useEffect(() => { localStorage.setItem('stakeout-currency', currency) }, [currency])

  useEffect(() => {
    let cancelled = false
    const load = () =>
      fetchFxRate('USD', 'INR')
        .then(r => { if (!cancelled) { setUsdInr(r.rate); setFxSource(r.source) } })
        .catch(() => {})
    load()
    const id = setInterval(load, 60 * 60_000) // refresh hourly
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  return (
    <PrefsContext.Provider value={{ market, setMarket, currency, setCurrency, usdInr, fxSource }}>
      {children}
    </PrefsContext.Provider>
  )
}

export const usePrefs = () => useContext(PrefsContext)
