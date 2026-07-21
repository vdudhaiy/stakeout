import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'

interface Props {
  info: Record<string, unknown>
}

export function StockInfoCard({ info }: Props) {
  const [expanded, setExpanded] = useState(false)

  const industry = info.industry as string | undefined
  const sector = info.sector as string | undefined
  const summary = info.longBusinessSummary as string | undefined

  if (!industry && !sector && !summary) return null

  const summaryLong = (summary?.length ?? 0) > 320

  return (
    <div className="shrink-0 bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
      {(sector || industry) && (
        <div className="flex items-center gap-2 flex-wrap">
          {sector && (
            <span className="px-2.5 py-1 bg-indigo-500/10 text-indigo-300 text-xs rounded-md border border-indigo-500/20 font-medium">
              {sector}
            </span>
          )}
          {industry && (
            <span className="px-2.5 py-1 bg-zinc-800 text-zinc-300 text-xs rounded-md border border-zinc-700">
              {industry}
            </span>
          )}
        </div>
      )}

      {summary && (
        <div>
          <p
            className="text-zinc-400 text-sm leading-relaxed"
            style={!expanded && summaryLong ? { display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' } : undefined}
          >
            {summary}
          </p>
          {summaryLong && (
            <button
              onClick={() => setExpanded(v => !v)}
              className="mt-1.5 flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
              {expanded ? 'Show less' : 'Show more'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
