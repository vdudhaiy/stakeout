/**
 * Supabase client (auth only — data lives behind the Stakeout API).
 *
 * When VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY are unset, the app runs in
 * "local mode": no accounts, everything maps to a single local user, exactly
 * like the original single-user desktop experience.
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

export const supabase: SupabaseClient | null =
  url && anonKey ? createClient(url, anonKey) : null

export const authEnabled = supabase !== null
