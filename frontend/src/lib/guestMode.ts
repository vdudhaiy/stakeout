/**
 * Whether the current tab is browsing as a guest — read directly from
 * sessionStorage rather than through a React-registered callback (like
 * setAuthTokenGetter). A registered getter updated via useEffect races: the
 * state flip in AuthContext and the resulting re-fetch in App.tsx land in
 * the same commit, and child effects fire before parent effects, so a
 * consumer could read the getter before AuthContext updates it. Reading
 * the flag straight from storage is synchronous and can't be stale.
 */
const GUEST_KEY = 'stakeout-guest-mode'

export function isGuestModeActive(): boolean {
  return sessionStorage.getItem(GUEST_KEY) === '1'
}

export function setGuestModeActive(active: boolean): void {
  if (active) sessionStorage.setItem(GUEST_KEY, '1')
  else sessionStorage.removeItem(GUEST_KEY)
}
