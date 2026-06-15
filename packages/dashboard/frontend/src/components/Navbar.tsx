import clsx from 'clsx'
import { TrendingUp, House, LayoutDashboard, Activity, Briefcase } from 'lucide-react'
import type { HealthStatus, View } from '../types'

interface Props {
  view: View
  onViewChange: (v: View) => void
  healthStatus: HealthStatus
  marketOpen: boolean | null
}

const NAV_ITEMS: Array<{
  view: View
  label: string
  icon: React.ElementType
  badge?: (healthStatus: HealthStatus) => React.ReactNode
}> = [
  { view: 'home', label: 'Home', icon: House },
  { view: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { view: 'portfolio', label: 'Portfolio', icon: Briefcase },
  {
    view: 'health',
    label: 'Health',
    icon: Activity,
    badge: (s: HealthStatus) => (
      <span
        className={clsx('w-1.5 h-1.5 rounded-full', {
          'bg-emerald-500': s === 'ok',
          'bg-red-500': s === 'error',
          'bg-yellow-400 animate-pulse': s === 'loading',
        })}
      />
    ),
  },
]

export function Navbar({ view, onViewChange, healthStatus, marketOpen }: Props) {
  return (
    <header className="flex items-center h-14 px-6 border-b border-zinc-800 bg-zinc-950 shrink-0 gap-8">
      <div className="flex items-center gap-2.5">
        <TrendingUp size={18} className="text-indigo-400" />
        <span className="text-white font-semibold tracking-tight">Market Lens</span>
      </div>

      <nav className="flex items-center gap-1">
        {NAV_ITEMS.map(({ view: v, label, icon: Icon, badge }) => (
          <button
            key={v}
            onClick={() => onViewChange(v)}
            className={clsx(
              'flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
              view === v
                ? 'bg-zinc-800 text-zinc-100'
                : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900',
            )}
          >
            <Icon size={14} />
            {label}
            {badge?.(healthStatus)}
          </button>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-2">
        <span
          className={clsx('w-2 h-2 rounded-full shrink-0', {
            'bg-emerald-500 animate-pulse': marketOpen === true,
            'bg-red-500': marketOpen === false,
            'bg-zinc-600': marketOpen === null,
          })}
        />
        <span className="text-xs font-medium text-zinc-400">
          {marketOpen === null ? 'Market —' : marketOpen ? 'Market Open' : 'Market Closed'}
        </span>
      </div>
    </header>
  )
}
