import { createContext, useContext, useState, useRef, useCallback, useEffect, type ReactNode } from 'react'

interface ThemeContextType {
  isDark: boolean
  toggleTheme: (x: number, y: number) => void
}

const ThemeContext = createContext<ThemeContextType>({ isDark: true, toggleTheme: () => {} })

interface RippleState {
  x: number
  y: number
  id: number
  toLight: boolean
}

function getInitialTheme(): boolean {
  const saved = localStorage.getItem('stakeout-theme') ?? localStorage.getItem('market-lens-theme')
  if (saved === 'light') return false
  if (saved === 'dark') return true
  return true // default dark
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [isDark, setIsDark] = useState(() => {
    const dark = getInitialTheme()
    // Apply immediately so the first render has the correct data-theme on <html>
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    return dark
  })
  const [ripple, setRipple] = useState<RippleState | null>(null)
  const idRef = useRef(0)

  // Keep <html> data-theme and localStorage in sync
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light')
    localStorage.setItem('stakeout-theme', isDark ? 'dark' : 'light')
  }, [isDark])

  const toggleTheme = useCallback((x: number, y: number) => {
    const id = ++idRef.current
    const toLight = isDark
    setRipple({ x, y, id, toLight })
    setTimeout(() => setIsDark(d => !d), 350)
    setTimeout(() => setRipple(r => (r?.id === id ? null : r)), 800)
  }, [isDark])

  return (
    <ThemeContext.Provider value={{ isDark, toggleTheme }}>
      {children}
      {ripple && (
        <div
          key={ripple.id}
          className={`cyberpunk-ripple ${ripple.toLight ? 'to-light' : 'to-dark'}`}
          style={{ left: ripple.x, top: ripple.y }}
        />
      )}
    </ThemeContext.Provider>
  )
}

export const useTheme = () => useContext(ThemeContext)
