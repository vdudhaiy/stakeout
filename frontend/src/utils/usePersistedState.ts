import { useEffect, useState } from 'react'

// useState backed by localStorage, namespaced under the app's `stakeout-`
// prefix (mirrors the pattern in PrefsContext). Meant for standalone bits of
// persisted UI state — e.g. a panel's collapsed/expanded state — that don't
// need to be shared via context.
export function usePersistedState<T>(key: string, defaultValue: T) {
  const storageKey = `stakeout-${key}`
  const [value, setValue] = useState<T>(() => {
    const raw = localStorage.getItem(storageKey)
    return raw != null ? (JSON.parse(raw) as T) : defaultValue
  })

  useEffect(() => {
    localStorage.setItem(storageKey, JSON.stringify(value))
  }, [storageKey, value])

  return [value, setValue] as const
}
