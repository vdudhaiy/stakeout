import { TrendingUp } from 'lucide-react'

export function Header() {
  return (
    <header className="flex items-center h-14 px-6 border-b border-zinc-800 bg-zinc-950 shrink-0">
      <div className="flex items-center gap-2.5">
        <TrendingUp size={18} className="text-indigo-400" />
        <span className="text-white font-semibold tracking-tight">Stakeout</span>
      </div>
    </header>
  )
}
