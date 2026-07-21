/**
 * Client for local-auth mode's email/password endpoints (/auth/signup,
 * /auth/login, /auth/logout) — only reachable when the backend has no
 * Supabase project configured. See AuthContext.tsx for how this plugs in
 * as an alternative to a real Supabase session.
 */
const API_BASE = ((import.meta.env.VITE_API_URL as string | undefined) ?? '').replace(/\/$/, '')

export interface LocalAuthResult {
  token: string
  email: string
}

async function post(path: string, body?: Record<string, unknown>, token?: string): Promise<Response> {
  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return fetch(`${API_BASE}${path}`, { method: 'POST', headers, body: body ? JSON.stringify(body) : undefined })
}

async function parseAuthResult(res: Response, fallback: string): Promise<LocalAuthResult> {
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: fallback }))
    throw new Error(err.detail ?? fallback)
  }
  return res.json()
}

export async function localSignUp(email: string, password: string): Promise<LocalAuthResult> {
  const res = await post('/auth/signup', { email, password })
  return parseAuthResult(res, 'Could not create an account')
}

export async function localSignIn(email: string, password: string): Promise<LocalAuthResult> {
  const res = await post('/auth/login', { email, password })
  return parseAuthResult(res, 'Invalid email or password')
}

export async function localSignOut(token: string): Promise<void> {
  await post('/auth/logout', undefined, token).catch(() => {})
}
