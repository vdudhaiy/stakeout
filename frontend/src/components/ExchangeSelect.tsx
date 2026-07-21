import clsx from 'clsx'
import { EXCHANGES, type Exchange } from '../utils/market'

interface Props {
  value: Exchange
  onChange: (exchange: Exchange) => void
}

/** Segmented control for picking the exchange a ticker trades on — drives
 * which suffix (.NS / .BO) the backend appends and which currency shows. */
export function ExchangeSelect({ value, onChange }: Props) {
  return (
    <div className="flex rounded-lg overflow-hidden border border-zinc-700">
      {EXCHANGES.map(({ value: v, label }) => (
        <button
          key={v}
          type="button"
          onClick={() => onChange(v)}
          className={clsx(
            'flex-1 px-2 py-1.5 text-xs font-medium transition-colors whitespace-nowrap',
            value === v
              ? 'bg-indigo-600 text-white'
              : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200',
          )}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
