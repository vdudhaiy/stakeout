import { ArrowRight, Check, Cloud, Copy, Github, HardDrive, Lock, Terminal } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { motion } from 'motion/react'
import clsx from 'clsx'
import { fadeUp } from '../lib/motion'

const REPO_URL = 'https://github.com/vdudhaiy/stakeout'

const DOCKER_CMDS = `git clone ${REPO_URL}.git
cd stakeout
docker compose up --build`

function CodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="relative rounded-lg bg-zinc-950 border border-zinc-800 font-mono text-xs">
      <button
        onClick={() => {
          navigator.clipboard.writeText(code).catch(() => {})
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        }}
        title="Copy commands"
        className="absolute right-2 top-2 flex items-center gap-1 px-2 py-1 rounded-md border border-zinc-700 text-zinc-500 hover:text-zinc-200 hover:border-zinc-500 transition-colors text-[0.625rem]"
      >
        {copied ? <Check size={10} className="text-emerald-400" /> : <Copy size={10} />}
        {copied ? 'Copied' : 'Copy'}
      </button>
      <pre className="p-4 pr-20 overflow-x-auto text-zinc-300 leading-relaxed">{code}</pre>
    </div>
  )
}

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2 text-xs text-zinc-400 leading-relaxed">
      <Check size={12} className="text-emerald-400 shrink-0 mt-0.5" />
      <span>{children}</span>
    </li>
  )
}

/** Explains the two ways of running Stakeout: this hosted site, or a
 * private local deployment via Docker. */
export function GetStartedPage() {
  const navigate = useNavigate()

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8 sm:space-y-10">

        {/* ── Header ─────────────────────────────────────────────────── */}
        <motion.div variants={fadeUp} initial="hidden" animate="show" custom={0} className="text-center">
          <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight text-zinc-100 mb-2">
            Two ways to use Stakeout
          </h1>
          <p className="text-zinc-400 text-sm max-w-2xl mx-auto leading-relaxed">
            Use it right here on the web with an account that syncs across devices, or clone the
            repository and run your own private copy on your machine. Same app, same features —
            you choose where your data lives.
          </p>
        </motion.div>

        {/* ── The two options ────────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-stretch">

          {/* Web platform */}
          <motion.div
            variants={fadeUp} initial="hidden" animate="show" custom={1}
            className="flex flex-col bg-zinc-900 border border-indigo-500/25 rounded-xl p-5 sm:p-6 space-y-4"
          >
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-indigo-500/10 border border-indigo-500/25">
                <Cloud size={19} className="text-indigo-400" />
              </div>
              <div>
                <h2 className="font-display text-zinc-100 font-semibold">Web platform</h2>
                <p className="text-[0.6875rem] text-zinc-500">This website — zero setup</p>
              </div>
              <span className="ml-auto text-[0.625rem] font-mono px-2 py-0.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 text-indigo-300">
                EASIEST
              </span>
            </div>

            <p className="text-xs text-zinc-400 leading-relaxed">
              You're already here. Sign in with Google, an email magic link, or a password and your
              watchlist and portfolios sync across devices — or click <span className="text-zinc-300">Continue as
              Guest</span> to try everything with nothing saved beyond your browser session.
            </p>

            <ul className="space-y-1.5">
              <Bullet>No installation, no accounts required to try (Guest Mode)</Bullet>
              <Bullet>Watchlist &amp; portfolios sync across your devices when signed in</Bullet>
              <Bullet>Always running the latest version</Bullet>
              <Bullet>Best for: everyday investors who just want to track their stakes</Bullet>
            </ul>

            <div className="mt-auto pt-2 flex items-center gap-2">
              <button
                onClick={() => navigate('/tracker')}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition-colors"
              >
                Open the tracker
                <ArrowRight size={13} />
              </button>
            </div>
          </motion.div>

          {/* Local / self-hosted */}
          <motion.div
            variants={fadeUp} initial="hidden" animate="show" custom={2}
            className="flex flex-col bg-zinc-900 border border-zinc-800 rounded-xl p-5 sm:p-6 space-y-4"
          >
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/25">
                <HardDrive size={19} className="text-emerald-400" />
              </div>
              <div>
                <h2 className="font-display text-zinc-100 font-semibold">Run it locally</h2>
                <p className="text-[0.6875rem] text-zinc-500">For developers &amp; the privacy-minded</p>
              </div>
              <span className="ml-auto flex items-center gap-1 text-[0.625rem] font-mono px-2 py-0.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-300">
                <Lock size={9} />
                MOST PRIVATE
              </span>
            </div>

            <p className="text-xs text-zinc-400 leading-relaxed">
              Clone the repository and run your own copy with Docker. Everything — accounts,
              portfolios, watchlists, price data — lives in a Postgres database on your machine
              and never leaves it. The code is open source, so you can also fork it and make it
              your own.
            </p>

            <div className="space-y-2">
              <p className="flex items-center gap-1.5 text-[0.625rem] font-semibold tracking-widest text-zinc-500">
                <Terminal size={11} /> QUICK START — REQUIRES DOCKER
              </p>
              <CodeBlock code={DOCKER_CMDS} />
              <p className="text-[0.6875rem] text-zinc-500">
                Then open <span className="font-mono text-zinc-300">http://localhost:3000</span>.
                Prefer running without Docker? The README covers a plain Python + Node dev setup too.
              </p>
            </div>

            <ul className="space-y-1.5">
              <Bullet>All data stays on your machine — nothing is sent to our servers</Bullet>
              <Bullet>Local accounts (or guest mode) with a persistent Postgres database</Bullet>
              <Bullet>Hack on it: MIT-licensed Python backend + React frontend</Bullet>
              <Bullet>Best for: developers, self-hosters, and anyone who wants full control</Bullet>
            </ul>

            <div className="mt-auto pt-2">
              <a
                href={REPO_URL}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-200 rounded-lg text-sm font-medium transition-colors"
              >
                <Github size={14} />
                View on GitHub
              </a>
            </div>
          </motion.div>
        </div>

        {/* ── Comparison ─────────────────────────────────────────────── */}
        {/* A three-column comparison can't usefully collapse — each cell is a
            sentence that only means something opposite its two siblings — so
            it keeps its shape and scrolls sideways below ~40rem instead. */}
        <motion.div variants={fadeUp} initial="hidden" animate="show" custom={3} className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
          <div className="grid grid-cols-3 text-xs min-w-[38rem]">
            <div className="px-4 py-2.5 border-b border-zinc-800 text-[0.625rem] font-semibold tracking-widest text-zinc-500">AT A GLANCE</div>
            <div className="px-4 py-2.5 border-b border-zinc-800 text-[0.625rem] font-semibold tracking-widest text-indigo-300">WEB PLATFORM</div>
            <div className="px-4 py-2.5 border-b border-zinc-800 text-[0.625rem] font-semibold tracking-widest text-emerald-300">LOCAL (DOCKER)</div>
            {([
              ['Setup', 'None — just open the site', 'Clone repo + docker compose up'],
              ['Where your data lives', 'Managed cloud database (or your browser in Guest Mode)', 'Postgres on your own machine'],
              ['Accounts', 'Google / email sign-in, syncs across devices', 'Local email/password accounts, or guest'],
              ['Updates', 'Automatic', 'git pull && docker compose up --build'],
              ['Cost', 'Free', 'Free (your own hardware)'],
            ] as const).map(([label, web, local], i, arr) => (
              <div key={label} className="contents">
                <div className={clsx('px-4 py-2.5 text-zinc-400 font-medium', i < arr.length - 1 && 'border-b border-zinc-800/60')}>{label}</div>
                <div className={clsx('px-4 py-2.5 text-zinc-500', i < arr.length - 1 && 'border-b border-zinc-800/60')}>{web}</div>
                <div className={clsx('px-4 py-2.5 text-zinc-500', i < arr.length - 1 && 'border-b border-zinc-800/60')}>{local}</div>
              </div>
            ))}
          </div>
          </div>
        </motion.div>

        <p className="text-center text-[0.6875rem] text-zinc-600">
          Both modes are the same open-source codebase. The cloud deployment guide (Vercel + Render + Supabase) is in the README for anyone who wants to host their own public instance.
        </p>
      </div>
    </div>
  )
}
