import clsx from 'clsx'
import { CheckCircle2, XCircle, Activity, Clock, Wifi, WifiOff } from 'lucide-react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import type { HealthStatus, LatencyRecord } from '../types'

interface Props {
  status: HealthStatus
  latencyMs: number | null
  lastChecked: Date | null
  history: LatencyRecord[]
}

function latencyColor(ms: number | null) {
  if (ms === null) return 'text-zinc-600'
  if (ms < 100) return 'text-emerald-400'
  if (ms < 300) return 'text-yellow-400'
  return 'text-red-400'
}

function latencyLabel(ms: number) {
  if (ms < 100) return 'Excellent'
  if (ms < 300) return 'Good'
  return 'Slow'
}

function StatCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 flex flex-col gap-3">
      <span className="text-[10px] text-zinc-500 tracking-widest font-medium">{label}</span>
      {children}
    </div>
  )
}

export function HealthDashboard({ status, latencyMs, lastChecked, history }: Props) {
  const isOnline = status === 'ok'
  const isLoading = status === 'loading'

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-5">
      {/* Stat cards */}
      <div className="grid grid-cols-3 gap-4">
        <StatCard label="API STATUS">
          <div className="flex items-center gap-2.5">
            {isOnline ? (
              <CheckCircle2 size={22} className="text-emerald-500" />
            ) : isLoading ? (
              <Activity size={22} className="text-yellow-400 animate-pulse" />
            ) : (
              <XCircle size={22} className="text-red-500" />
            )}
            <span
              className={clsx(
                'text-xl font-semibold',
                isOnline ? 'text-emerald-400' : isLoading ? 'text-yellow-400' : 'text-red-400',
              )}
            >
              {isOnline ? 'Online' : isLoading ? 'Connecting' : 'Offline'}
            </span>
          </div>
        </StatCard>

        <StatCard label="LATENCY">
          <div className="flex items-baseline gap-1.5">
            <span className={clsx('text-3xl font-mono font-semibold', latencyColor(latencyMs))}>
              {latencyMs !== null ? latencyMs : '—'}
            </span>
            {latencyMs !== null && (
              <span className="text-zinc-500 text-sm font-mono">ms</span>
            )}
          </div>
          {latencyMs !== null && (
            <span className={clsx('text-xs font-medium', latencyColor(latencyMs))}>
              {latencyLabel(latencyMs)}
            </span>
          )}
        </StatCard>

        <StatCard label="LAST CHECKED">
          <div className="flex items-center gap-2">
            <Clock size={16} className="text-zinc-500 shrink-0" />
            <span className="font-mono text-zinc-200 text-base">
              {lastChecked ? lastChecked.toLocaleTimeString() : '—'}
            </span>
          </div>
          {lastChecked && (
            <span className="text-xs text-zinc-500">{lastChecked.toLocaleDateString()}</span>
          )}
        </StatCard>
      </div>

      {/* Latency history chart */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
        <p className="text-[10px] text-zinc-500 tracking-widest font-medium mb-4">
          LATENCY HISTORY
        </p>
        {history.length < 2 ? (
          <div className="h-52 flex items-center justify-center text-zinc-600 text-sm">
            Collecting data — checks run every 30 s
          </div>
        ) : (
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={history} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="latencyGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis
                  dataKey="time"
                  tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                  tickLine={false}
                  axisLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                  tickLine={false}
                  axisLine={false}
                  width={52}
                  tickFormatter={v => `${v}ms`}
                />
                <Tooltip
                  formatter={(v: number) => [`${v} ms`, 'Latency']}
                  contentStyle={{
                    background: '#18181b',
                    border: '1px solid #3f3f46',
                    borderRadius: 8,
                    fontSize: 12,
                    fontFamily: 'JetBrains Mono',
                  }}
                  labelStyle={{ color: '#a1a1aa' }}
                  itemStyle={{ color: '#818cf8' }}
                />
                <ReferenceLine y={100} stroke="#10b98133" strokeDasharray="4 4" />
                <ReferenceLine y={300} stroke="#f59e0b33" strokeDasharray="4 4" />
                <Area
                  type="monotone"
                  dataKey="latencyMs"
                  stroke="#6366f1"
                  strokeWidth={1.5}
                  fill="url(#latencyGradient)"
                  dot={false}
                  activeDot={{ r: 3, strokeWidth: 0, fill: '#6366f1' }}
                  connectNulls={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
        <div className="flex items-center gap-5 mt-3 text-[11px] text-zinc-600">
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-5 border-t border-dashed border-emerald-500/40" />
            100 ms
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-5 border-t border-dashed border-yellow-500/40" />
            300 ms
          </span>
        </div>
      </div>

      {/* Recent checks table */}
      {history.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <div className="px-5 py-3.5 border-b border-zinc-800">
            <p className="text-[10px] text-zinc-500 tracking-widest font-medium">RECENT CHECKS</p>
          </div>
          <div className="divide-y divide-zinc-800/60">
            {[...history]
              .reverse()
              .slice(0, 10)
              .map((record, i) => (
                <div key={i} className="grid grid-cols-3 items-center px-5 py-3 text-xs">
                  <span className="font-mono text-zinc-400">{record.time}</span>
                  <span
                    className={clsx(
                      'flex items-center gap-1.5',
                      record.status === 'ok' ? 'text-emerald-400' : 'text-red-400',
                    )}
                  >
                    {record.status === 'ok' ? (
                      <Wifi size={11} />
                    ) : (
                      <WifiOff size={11} />
                    )}
                    {record.status === 'ok' ? 'Online' : 'Offline'}
                  </span>
                  <span className={clsx('font-mono font-medium', latencyColor(record.latencyMs))}>
                    {record.latencyMs !== null ? `${record.latencyMs} ms` : '—'}
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}
