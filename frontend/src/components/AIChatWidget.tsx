import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { Bot, MessageCircle, RefreshCw, Send, Trash2, X } from 'lucide-react'
import { sendChatMessage } from '../api'
import type { ChatContext, ChatMessage } from '../types'

interface Props {
  context: ChatContext
}

const GREETING = "Hi! I can explain what the indicators and news on this page mean, in plain English. I won't tell you to buy or sell anything — just help you understand the data."

function contextLabel(context: ChatContext): string | null {
  if (context.kind === 'stock') return `Talking about ${context.ticker}`
  if (context.kind === 'portfolio') return 'Talking about your portfolio'
  return null
}

export function AIChatWidget({ context }: Props) {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, loading, error])

  function clearChat() {
    setMessages([])
    setError(null)
  }

  async function send() {
    const text = input.trim()
    if (!text || loading) return
    const history = messages
    setMessages(m => [...m, { role: 'user', content: text }])
    setInput('')
    setError(null)
    setLoading(true)
    try {
      const res = await sendChatMessage(text, context, history)
      setMessages(m => [...m, { role: 'assistant', content: res.reply }])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to reach the AI assistant')
    } finally {
      setLoading(false)
    }
  }

  const chip = contextLabel(context)

  return (
    <>
      {open && (
        <div className="fixed bottom-40 right-6 z-50 w-96 max-w-[calc(100vw-3rem)] h-[520px] max-h-[calc(100vh-12rem)] bg-zinc-950 border border-zinc-700 rounded-xl shadow-2xl flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex items-center gap-2 px-4 py-3 border-b border-zinc-800 shrink-0">
            <Bot size={15} className="text-indigo-400" />
            <span className="text-sm font-semibold text-zinc-100">Stakeout AI</span>
            {chip && (
              <span className="ml-1 px-2 py-0.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 text-indigo-300 text-[10px] font-medium">
                {chip}
              </span>
            )}
            <button
              onClick={clearChat}
              disabled={messages.length === 0 || loading}
              title="Clear chat"
              aria-label="Clear chat"
              className="ml-auto text-zinc-500 hover:text-zinc-300 disabled:opacity-30 disabled:hover:text-zinc-500 transition-colors"
            >
              <Trash2 size={14} />
            </button>
            <button
              onClick={() => setOpen(false)}
              aria-label="Close chat"
              className="text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              <X size={15} />
            </button>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-2.5">
            <div className="max-w-[85%] rounded-lg px-3 py-2 text-xs leading-relaxed bg-zinc-800 text-zinc-300">
              {GREETING}
            </div>
            {messages.map((m, i) => (
              <div
                key={i}
                className={clsx(
                  'max-w-[85%] rounded-lg px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap',
                  m.role === 'user'
                    ? 'ml-auto bg-indigo-600 text-white'
                    : 'bg-zinc-800 text-zinc-200',
                )}
              >
                {m.content}
              </div>
            ))}
            {loading && (
              <div className="flex items-center gap-1.5 bg-zinc-800 text-zinc-500 rounded-lg px-3 py-2 w-fit">
                <RefreshCw size={11} className="animate-spin" />
                <span className="text-xs">Thinking… (local models can take up to a minute)</span>
              </div>
            )}
            {error && (
              <div className="text-xs text-zinc-500 px-1">
                AI chat is unavailable right now — {error.toLowerCase().includes('ollama') ? error : 'the local AI service may be offline.'}
              </div>
            )}
          </div>

          {/* Input */}
          <div className="border-t border-zinc-800 p-3 shrink-0 space-y-1.5">
            <div className="flex items-center gap-2">
              <input
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') send() }}
                placeholder="Ask about this stock or your portfolio…"
                disabled={loading}
                className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-indigo-500/50 disabled:opacity-50"
              />
              <button
                onClick={send}
                disabled={loading || !input.trim()}
                aria-label="Send message"
                className="flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-40 transition-colors shrink-0"
              >
                <Send size={13} />
              </button>
            </div>
            <p className="text-[10px] text-zinc-600 text-center">AI-generated · not financial advice</p>
          </div>
        </div>
      )}

      <button
        onClick={() => setOpen(o => !o)}
        aria-label={open ? 'Close AI chat' : 'Open AI chat'}
        className="fixed bottom-24 right-6 z-50 flex items-center justify-center w-12 h-12 rounded-full bg-indigo-600 hover:bg-indigo-500 text-white shadow-2xl transition-colors"
      >
        {open ? <X size={19} /> : <MessageCircle size={19} />}
      </button>
    </>
  )
}
