import { useState, useEffect, useRef } from 'react'
import clsx from 'clsx'
import { Search, ChevronDown, ChevronRight, BarChart2, PlusCircle, Check, X } from 'lucide-react'
import { fetchAllStocks, fetchIndustryMap, fetchSectorMap, addStock } from '../api'
import type { GroupedStocks, ComparisonGroup } from '../types'

type SidebarTab = 'general' | 'industry' | 'sector'

interface Props {
  selected: string
  tickers: string[]
  onSelect: (ticker: string) => void
  onCompare: (group: ComparisonGroup) => void
  onTickersUpdated: (tickers: string[]) => void
  onAdded?: (ticker: string) => void
}

function GroupSection({
  name,
  tickers,
  type,
  selected,
  onSelect,
  onCompare,
}: {
  name: string
  tickers: string[]
  type: 'industry' | 'sector'
  selected: string
  onSelect: (t: string) => void
  onCompare: (g: ComparisonGroup) => void
}) {
  const [open, setOpen] = useState(true)

  return (
    <div>
      <div className="group flex items-center px-3 py-2 hover:bg-zinc-900/50 transition-colors">
        <button
          onClick={() => setOpen(o => !o)}
          className="flex items-center gap-1 flex-1 min-w-0 text-left"
        >
          {open
            ? <ChevronDown size={11} className="shrink-0 text-zinc-500" />
            : <ChevronRight size={11} className="shrink-0 text-zinc-500" />
          }
          <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider truncate ml-0.5">
            {name}
          </span>
          <span className="ml-1.5 text-[10px] text-zinc-600 shrink-0">{tickers.length}</span>
        </button>
        <button
          onClick={e => { e.stopPropagation(); onCompare({ name, tickers, type }) }}
          title={`Compare ${type}`}
          className="opacity-0 group-hover:opacity-100 p-1 rounded text-zinc-500 hover:text-indigo-400 hover:bg-zinc-800 transition-all shrink-0"
        >
          <BarChart2 size={12} />
        </button>
      </div>
      {open && tickers.map(ticker => (
        <button
          key={ticker}
          onClick={() => onSelect(ticker)}
          className={clsx(
            'w-full flex items-center pl-8 pr-3 py-2 text-left transition-colors',
            selected === ticker
              ? 'bg-indigo-500/10 text-indigo-300 border-r-2 border-indigo-500'
              : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200',
          )}
        >
          <span className="font-mono text-sm font-medium">{ticker}</span>
        </button>
      ))}
    </div>
  )
}

export function TickerSidebar({ selected, tickers, onSelect, onCompare, onTickersUpdated, onAdded }: Props) {
  const [tab, setTab] = useState<SidebarTab>('general')
  const [search, setSearch] = useState('')
  const [industryMap, setIndustryMap] = useState<GroupedStocks | null>(null)
  const [sectorMap, setSectorMap] = useState<GroupedStocks | null>(null)
  const [groupLoading, setGroupLoading] = useState(false)
  const [adding, setAdding] = useState(false)
  const [addValue, setAddValue] = useState('')
  const [addError, setAddError] = useState<string | null>(null)
  const [addLoading, setAddLoading] = useState(false)
  const [existNotice, setExistNotice] = useState(false)
  const addInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (tab === 'industry' && industryMap === null) {
      setGroupLoading(true)
      fetchIndustryMap().then(setIndustryMap).catch(() => {}).finally(() => setGroupLoading(false))
    } else if (tab === 'sector' && sectorMap === null) {
      setGroupLoading(true)
      fetchSectorMap().then(setSectorMap).catch(() => {}).finally(() => setGroupLoading(false))
    }
  }, [tab, industryMap, sectorMap])

  function openAdd() {
    setAdding(true)
    setAddValue('')
    setAddError(null)
    setTimeout(() => addInputRef.current?.focus(), 0)
  }

  function cancelAdd() {
    setAdding(false)
    setAddValue('')
    setAddError(null)
  }

  async function submitAdd() {
    const ticker = addValue.trim().toUpperCase()
    if (!ticker) return
    setAddLoading(true)
    setAddError(null)
    try {
      const result = await addStock(ticker)
      if (result.exist) {
        cancelAdd()
        onSelect(ticker)
        setExistNotice(true)
        setTimeout(() => setExistNotice(false), 3500)
      } else {
        const updated = await fetchAllStocks()
        onTickersUpdated(updated)
        cancelAdd()
        onSelect(ticker)
        onAdded?.(ticker)
      }
    } catch (e) {
      setAddError(e instanceof Error ? e.message : 'Failed to add ticker')
    } finally {
      setAddLoading(false)
    }
  }

  const q = search.toUpperCase()
  const filteredTickers = tickers.filter(t => t.includes(q))

  function filteredGroups(map: GroupedStocks): [string, string[]][] {
    return Object.entries(map)
      .map(([name, tickers]) => {
        const matching = q ? tickers.filter(t => t.includes(q)) : tickers
        return [name, matching] as [string, string[]]
      })
      .filter(([, tickers]) => tickers.length > 0)
  }

  const activeMap = tab === 'industry' ? industryMap : tab === 'sector' ? sectorMap : null

  return (
    <aside className="w-64 shrink-0 border-r border-zinc-800 bg-zinc-950 flex flex-col">
      {existNotice && (
        <div className="mx-3 mt-2 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-mono">
          Already tracked — navigated to stock.
        </div>
      )}
      {/* Tab switcher */}
      <div className="flex border-b border-zinc-800 shrink-0">
        {(['general', 'industry', 'sector'] as SidebarTab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              'flex-1 py-2.5 text-[11px] font-medium transition-colors capitalize',
              tab === t
                ? 'text-indigo-400 border-b-2 border-indigo-500 bg-indigo-500/5'
                : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900/50',
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Search + Add */}
      <div className="p-3 border-b border-zinc-800 shrink-0 flex flex-col gap-2">
        <div className="flex items-center gap-1.5">
          <div className="relative flex-1">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-600" />
            <input
              type="text"
              placeholder="Search..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full bg-zinc-900 text-zinc-200 text-xs rounded pl-7 pr-3 py-2 outline-none border border-zinc-800 focus:border-indigo-500 transition-colors placeholder-zinc-600 font-mono"
            />
          </div>
          <button
            onClick={adding ? cancelAdd : openAdd}
            title={adding ? 'Cancel' : 'Add ticker'}
            className={clsx(
              'p-1.5 rounded transition-colors shrink-0',
              adding
                ? 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800'
                : 'text-zinc-500 hover:text-indigo-400 hover:bg-zinc-900',
            )}
          >
            {adding ? <X size={14} /> : <PlusCircle size={14} />}
          </button>
        </div>

        {adding && (
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-1">
              <input
                ref={addInputRef}
                type="text"
                placeholder="Ticker (e.g. AAPL)"
                value={addValue}
                onChange={e => { setAddValue(e.target.value.toUpperCase()); setAddError(null) }}
                onKeyDown={e => {
                  if (e.key === 'Enter') submitAdd()
                  if (e.key === 'Escape') cancelAdd()
                }}
                disabled={addLoading}
                className="flex-1 bg-zinc-900 text-zinc-200 text-xs rounded px-2.5 py-2 outline-none border border-zinc-700 focus:border-indigo-500 transition-colors placeholder-zinc-600 font-mono uppercase disabled:opacity-50"
              />
              <button
                onClick={submitAdd}
                disabled={addLoading || !addValue.trim()}
                title="Confirm"
                className="p-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
              >
                <Check size={13} />
              </button>
            </div>
            {addError && (
              <p className="text-[11px] text-red-400 px-0.5">{addError}</p>
            )}
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto py-1">
        {tab === 'general' && (
          filteredTickers.length === 0
            ? <p className="text-zinc-600 text-xs text-center py-4">No results</p>
            : <>
                <div className="group flex items-center px-3 py-2 border-b border-zinc-800/50 hover:bg-zinc-900/50 transition-colors">
                  <span className="flex-1 text-[11px] font-semibold text-zinc-400 uppercase tracking-wider">
                    All Stocks
                  </span>
                  <span className="text-[10px] text-zinc-600 mr-1.5">{filteredTickers.length}</span>
                  <button
                    onClick={() => onCompare({ name: 'All Stocks', tickers: filteredTickers, type: 'all' })}
                    title="Compare all stocks"
                    className="opacity-0 group-hover:opacity-100 p-1 rounded text-zinc-500 hover:text-indigo-400 hover:bg-zinc-800 transition-all shrink-0"
                  >
                    <BarChart2 size={12} />
                  </button>
                </div>
                {filteredTickers.map(ticker => (
                  <button
                    key={ticker}
                    onClick={() => onSelect(ticker)}
                    className={clsx(
                      'w-full flex items-center px-4 py-2.5 text-left transition-colors',
                      selected === ticker
                        ? 'bg-indigo-500/10 text-indigo-300 border-r-2 border-indigo-500'
                        : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200',
                    )}
                  >
                    <span className="font-mono text-sm font-medium">{ticker}</span>
                  </button>
                ))}
              </>
        )}

        {(tab === 'industry' || tab === 'sector') && (
          groupLoading
            ? <p className="text-zinc-600 text-xs text-center py-4">Loading...</p>
            : activeMap === null
              ? <p className="text-zinc-600 text-xs text-center py-4">No data</p>
              : filteredGroups(activeMap).length === 0
                ? <p className="text-zinc-600 text-xs text-center py-4">No results</p>
                : filteredGroups(activeMap).map(([name, tickers]) => (
                  <GroupSection
                    key={name}
                    name={name}
                    tickers={tickers}
                    type={tab === 'industry' ? 'industry' : 'sector'}
                    selected={selected}
                    onSelect={onSelect}
                    onCompare={onCompare}
                  />
                ))
        )}
      </div>
    </aside>
  )
}
