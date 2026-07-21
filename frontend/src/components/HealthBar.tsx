import clsx from 'clsx'
import { Wifi, WifiOff, Activity, Clock } from 'lucide-react'
import type { HealthStatus } from '../types'

interface Props {
  status: HealthStatus
  latencyMs: number | null
  lastChecked: Date | null
}

function LatencyColor(ms: number | null) {
  if (ms === null) return 'text-zinc-600'
  if (ms < 100) return 'text-emerald-400'
  if (ms < 300) return 'text-yellow-400'
  return 'text-red-400'
}

function Divider() {
  return <div className="w-px h-4 bg-zinc-800" />
}

export function HealthBar({ status, latencyMs, lastChecked }: Props) {
  const isOnline = status === 'ok'
  const isLoading = status === 'loading'

  return (
    <div className="flex items-center gap-5 h-9 px-6 border-b border-zinc-800/60 bg-zinc-900/40 text-xs shrink-0">
      {/* Status */}
      <div className="flex items-center gap-2">
        {isOnline ? (
          <Wifi size={12} className="text-emerald-500" />
        ) : isLoading ? (
          <Activity size={12} className="text-yellow-400 animate-pulse" />
        ) : (
          <WifiOff size={12} className="text-red-500" />
        )}
        <span
          className={clsx(
            'font-medium',
            isOnline ? 'text-emerald-400' : isLoading ? 'text-yellow-400' : 'text-red-400',
          )}
        >
          {isOnline ? 'Backend Online' : isLoading ? 'Connecting...' : 'Backend Offline'}
        </span>
      </div>

      <Divider />

      {/* Latency */}
      <div className="flex items-center gap-2">
        <span className="text-zinc-500">Latency</span>
        <span className={clsx('font-mono font-medium', LatencyColor(latencyMs))}>
          {latencyMs !== null ? `${latencyMs} ms` : '—'}
        </span>
      </div>

      {lastChecked && (
        <>
          <Divider />
          <div className="flex items-center gap-2 text-zinc-500">
            <Clock size={11} />
            <span>
              Last checked{' '}
              <span className="font-mono text-zinc-400">
                {lastChecked.toLocaleTimeString()}
              </span>
            </span>
          </div>
        </>
      )}
    </div>
  )
}
