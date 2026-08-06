import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { ChevronDown, ChevronUp, RefreshCw, Sparkles } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { fetchStockExplanation } from '../api'
import type { StockExplanationResponse } from '../types'
import { collapse } from '../lib/motion'

interface Props {
  ticker: string
}

const CONFIDENCE_STYLE: Record<string, string> = {
  high: 'bg-emerald-500',
  medium: 'bg-amber-400',
  low: 'bg-zinc-500',
}

const RSI_ZONE_LABEL: Record<string, string> = {
  overbought: 'Overbought',
  oversold: 'Oversold',
  neutral: 'Neutral',
}

const BOLLINGER_LABEL: Record<string, string> = {
  above_upper: 'Above upper band',
  upper_half: 'Upper half of the bands',
  lower_half: 'Lower half of the bands',
  below_lower: 'Below lower band',
}

const MACD_LABEL: Record<string, string> = {
  bullish_cross: 'Bullish crossover',
  bearish_cross: 'Bearish crossover',
  above_signal: 'Above signal line',
  below_signal: 'Below signal line',
}

const SMA_TREND_LABEL: Record<string, string> = {
  above_both: 'Above 50- & 200-day average',
  below_both: 'Below 50- & 200-day average',
  mixed: 'Mixed vs. 50-/200-day average',
}

function timeAgo(iso: string): string {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60_000))
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

function FactRow({ label, value }: { label: string; value: string | null }) {
  if (value == null) return null
  return (
    <div className="flex items-center justify-between gap-4 text-xs py-1">
      <span className="text-zinc-500">{label}</span>
      <span className="text-zinc-300 font-mono text-right">{value}</span>
    </div>
  )
}

export function AIInsightCard({ ticker }: Props) {
  const [explanation, setExplanation] = useState<StockExplanationResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [factsOpen, setFactsOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    setExplanation(null)
    setError(null)
    setFactsOpen(false)
    setLoading(true)
    fetchStockExplanation(ticker)
      .then(res => { if (!cancelled) setExplanation(res) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load AI insight') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [ticker])

  async function regenerate() {
    setRefreshing(true)
    setError(null)
    try {
      setExplanation(await fetchStockExplanation(ticker, true))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load AI insight')
    } finally {
      setRefreshing(false)
    }
  }

  const facts = explanation?.facts

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <Sparkles size={13} className="text-indigo-400 shrink-0" />
        <p className="text-[0.625rem] text-zinc-500 tracking-widest font-medium">AI INSIGHT</p>
        {explanation && (
          <span className="flex items-center gap-1.5 ml-1">
            <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', CONFIDENCE_STYLE[explanation.confidence])} />
            <span className="text-[0.625rem] text-zinc-500 capitalize">{explanation.confidence} confidence</span>
          </span>
        )}
        <button
          onClick={regenerate}
          disabled={loading || refreshing}
          title="Regenerate insight"
          className="ml-auto text-zinc-600 hover:text-zinc-400 disabled:opacity-40 transition-colors"
        >
          <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''} />
        </button>
      </div>

      {error ? (
        <div className="py-2">
          <p className="text-xs text-zinc-500">
            AI insight is unavailable right now — {error.toLowerCase().includes('ollama') ? error : 'the local AI service may be offline.'}
          </p>
          <button onClick={regenerate} className="mt-2 text-xs text-indigo-400 hover:text-indigo-300 transition-colors">
            Try again
          </button>
        </div>
      ) : loading ? (
        <div className="space-y-2 py-1">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className={clsx('h-3 rounded bg-zinc-800/60 animate-pulse', i === 2 && 'w-2/3')} />
          ))}
          <p className="text-[0.625rem] text-zinc-600 pt-1">Generating with a local AI model — this can take up to a minute.</p>
        </div>
      ) : explanation ? (
        <>
          <p className="text-sm text-zinc-300 leading-relaxed">{explanation.summary}</p>

          <button
            onClick={() => setFactsOpen(v => !v)}
            className="mt-3 flex items-center gap-1 text-[0.6875rem] text-indigo-400 hover:text-indigo-300 transition-colors"
          >
            {factsOpen ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
            {factsOpen ? 'Hide the numbers' : 'View the numbers'}
          </button>

          <AnimatePresence>
            {factsOpen && facts && (
              <motion.div variants={collapse} initial="hidden" animate="show" exit="exit" style={{ overflow: 'hidden' }}>
                <div className="mt-2 divide-y divide-zinc-800/70 border-t border-zinc-800/70">
                  <FactRow label="Close" value={`${facts.close.toFixed(2)}${facts.change_pct != null ? ` (${facts.change_pct >= 0 ? '+' : ''}${facts.change_pct.toFixed(2)}%)` : ''}`} />
                  <FactRow label="RSI (14)" value={facts.rsi != null ? `${facts.rsi.toFixed(1)}${facts.rsi_zone ? ` · ${RSI_ZONE_LABEL[facts.rsi_zone] ?? facts.rsi_zone}` : ''}` : null} />
                  <FactRow label="Bollinger" value={facts.bollinger_position ? BOLLINGER_LABEL[facts.bollinger_position] ?? facts.bollinger_position : null} />
                  <FactRow label="MACD" value={facts.macd_signal ? MACD_LABEL[facts.macd_signal] ?? facts.macd_signal : null} />
                  <FactRow label="Trend" value={facts.sma_trend ? SMA_TREND_LABEL[facts.sma_trend] ?? facts.sma_trend : null} />
                  <FactRow label="Volume vs. 20d avg" value={facts.volume_vs_avg_pct != null ? `${facts.volume_vs_avg_pct >= 0 ? '+' : ''}${facts.volume_vs_avg_pct.toFixed(1)}%` : null} />
                  {facts.rsi_recovery && (
                    <FactRow
                      label={`RSI recovery (${facts.rsi_recovery.horizon_days}d)`}
                      value={`${facts.rsi_recovery.recovered_pct.toFixed(0)}% of ${facts.rsi_recovery.occurrences} past occurrences`}
                    />
                  )}
                  <FactRow label="History" value={`${facts.history_days} trading days`} />
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <p className="mt-3 pt-3 border-t border-zinc-800 text-[0.625rem] text-zinc-600">
            Generated {timeAgo(explanation.generated_at)} · {explanation.model} · AI-generated from computed indicators, not financial advice.
          </p>
        </>
      ) : null}
    </div>
  )
}
