/**
 * Supabase client (auth only — data lives behind the Stakeout API).
 *
 * VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY are required for a working
 * deployment — the backend always requires a valid Supabase session for
 * user-scoped data. Visitors who don't want an account can use guest mode
 * instead (see contexts/AuthContext.tsx), which never touches these.
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

export const supabase: SupabaseClient | null =
  url && anonKey ? createClient(url, anonKey) : null

export const authEnabled = supabase !== null
