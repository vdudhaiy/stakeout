# Stakeout

**Open markets, open source.**

A free, open-source stock tracker for US and Indian markets. Use the hosted web platform with multi-user accounts, or run your own fully private copy locally with Docker.

[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-3b82f6)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-20%2B-84cc16)](https://nodejs.org/)
[![Platforms](https://img.shields.io/badge/platforms-Web-8b5cf6)]()

---

## What Is Stakeout?

Stakeout is a free, open-source app built for everyday people who want to keep watch on their stakes in the market — without paying for a Bloomberg terminal or a SaaS subscription.

You get a clean tracker with price charts, technical indicators, analyst insights, earnings history, a week of layered news headlines (company, industry, sector, and market), peer comparison, major US/India index charts, and a two-market portfolio tracker (US and India) with FIFO cost basis and sector/industry breakdowns — all powered by publicly available data.

There are **two ways to use Stakeout** (also explained in-app on the **Get Started** page):

1. **Web platform** — the hosted site. Google / email sign-in with per-user watchlists and portfolios that sync across devices, or **Guest Mode** with nothing saved beyond the browser session. Zero setup.
2. **Local / self-hosted (Docker)** — the most private option, aimed at developers. Clone the repo and `docker compose up`: everything (accounts, portfolios, price data) lives in a Postgres database on your own machine and never leaves it.

You can also deploy your own public instance to Vercel + Render + Supabase — see [Deploying to the Cloud](#deploying-to-the-cloud-vercel--render--supabase).

You're also encouraged to fork this project and build your own version. The codebase is intentionally approachable — a Python backend and a React frontend.

> [!WARNING]
> **Not financial advice.** Stakeout is for informational and educational purposes only. Nothing displayed in this application constitutes financial, investment, or trading advice. Always do your own research and consult a qualified financial professional before making any investment decisions.
>
> **Data source disclaimers.**
> - Market data is fetched via [yfinance](https://github.com/ranaroussi/yfinance), an open-source library that retrieves data from Yahoo Finance. This data may be delayed, incomplete, or inaccurate. Use of Yahoo Finance data is subject to [Yahoo Finance's Terms of Service](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) and is intended for personal, non-commercial use only.
> - News headlines are sourced from the [GDELT Project](https://www.gdeltproject.org/) (free, no API key) with Yahoo Finance as a fallback.
> - USD/INR exchange rates come from [Frankfurter](https://frankfurter.dev/) (ECB reference rates) with fallbacks. Rates are indicative daily references, not live trading rates.

---

## Features

- **Two markets, two portfolios** — track NYSE/NASDAQ and NSE/BSE stocks side by side. Indian tickers use Yahoo's `.NS` / `.BO` suffixes (e.g. `TCS.NS`, `RELIANCE.NS`). Each market gets its own portfolio, market-hours logic (ET vs IST), and native currency.
- **Currency switching** — a USD/INR dropdown in the navbar converts every displayed price using a daily ECB reference rate, with Indian digit grouping (₹1,23,456.78) when INR is selected.
- **Interactive price & volume charts** — 1-day intraday to 3 years, candlestick or area mode, with SMA/EMA overlays, Bollinger Bands, RSI and MACD oscillator panels.
- **Explain-everything (?) buttons** — every statistic in the app (OHLC, RSI, FIFO cost basis, analyst upside, …) has a small `?` popover with a plain-language explanation.
- **Layered news carousel** — the home page shows US and India market headlines; each stock's tracker page shows a horizontally scrollable carousel (with ‹ › controls) of the last 7 days of headlines about the company, its industry, its sector, and its market — newest first, all clickable through to the source.
- **Live price updates** — refreshes every 2 minutes while that stock's home exchange is open; pre-market data shown with timezone info.
- **Analyst insights** — price target range bar with upside %, recommendation drift (Strong Buy → Strong Sell), and EPS/revenue estimates for upcoming quarters.
- **Earnings & revenue history** — bar charts with Growth %, Surprise %, and Actual toggles.
- **Peer comparison** — normalized % change chart to compare stocks in the same industry or sector.
- **Portfolio tracker** — FIFO cost basis, unrealized/realized P&L per holding, allocation donut, interactive sector & industry breakdown pies (by invested value or by holdings count, per US/India portfolio), and one-click Excel export — per market.
- **Watchlist with market filter** — organize by industry/sector tabs, filter All / US / India; a ticker-tape marquee streams your watchlist's latest prices under the navbar.
- **Multi-user accounts** — Google OAuth, email magic-link, or email/password sign-in via Supabase; each user gets their own watchlist and portfolios. **Guest Mode** lets anyone try the app without signing in — watchlist and portfolio data stay in the browser for that session and are never written to the database.
- **AI-powered explanations (optional)** — a per-stock "AI Insight" card that explains what the indicators and news mean in plain English, plus a floating chat aware of whatever stock or portfolio you're looking at. Both run against a local [Ollama](https://ollama.com) model, so nothing about your stocks or portfolio leaves your machine; if Ollama isn't reachable, both features degrade gracefully to an "unavailable" message.
- **Dual market status pill** — NYSE and NSE open/closed at a glance, with session times in ET/IST and your local timezone.
- **Major index charts** — the home page shows the S&P 500, Dow Jones, NASDAQ, NIFTY 50, SENSEX, and NIFTY Bank with 3-month sparklines and day change, no sign-in needed.
- **Account settings** — click your avatar (top right) for an account summary popup and a settings page: theme, default market, portfolio exports, sign-out, and permanent account deletion.
- **Dark/light themes, smart caching** — a paper-ledger light theme and terminal-dark theme; TTL caches for quotes (60 s), news (15 min), FX (1 h), index quotes (10 min), and sector/industry classification (24 h) to stay well within free-tier data source limits.

---

## Quick Start — Docker (local / self-hosted)

The fastest way to run your own private Stakeout. Requires only [Docker](https://docs.docker.com/get-docker/) (with Compose v2).

```bash
git clone https://github.com/vdudhaiy/stakeout.git
cd stakeout
docker compose up --build      # or: make docker-up
```

Open **http://localhost:3000**. That's it — no `.env` needed.

What the stack runs:

| Service | What it is |
|---------|------------|
| `db` | Postgres 16 with a persistent volume (`stakeout-pgdata`) — your accounts and portfolios survive restarts |
| `backend` | The FastAPI API; runs `alembic upgrade head` automatically on start |
| `frontend` | nginx serving the built React app and proxying API calls to the backend (single origin, no CORS) |

Because no Supabase project is configured, the backend automatically runs its own **local email/password accounts** (stored in your Postgres container) — or click **Continue as Guest** to use the app with nothing saved server-side. All data stays on your machine.

Handy commands (run `make help` any time to list all of them):

```bash
make docker-up      # build + start in the background
make docker-logs    # follow logs
make docker-down    # stop (data kept)
make docker-reset   # stop AND delete the Postgres volume (wipes local data)
```

> [!NOTE]
> The Docker stack is for local/self-hosted use. It is entirely independent of the cloud deployment below — you can use either or both.

---

## Quick Start — Development Setup

### Prerequisites

- [Python 3.12+](https://www.python.org/downloads/)
- [Node.js 20+](https://nodejs.org/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/vdudhaiy/stakeout.git
cd stakeout

# 2. Install Python dependencies
make install           # equivalent to: uv sync

# 3. Install frontend dependencies
cd frontend
npm install
cd ..

# 4. Set up environment variables
cp .env.example .env   # then edit .env as needed

# 5. Start the backend server (Terminal 1)
make backend           # FastAPI at http://127.0.0.1:8000

# 6. Start the frontend dev server (Terminal 2)
make frontend          # React at http://localhost:5173
```

Open **http://localhost:5173** in your browser. Add a ticker (e.g. `AAPL`, or an Indian ticker like `TCS.NS`) — stock data downloads from Yahoo Finance on demand the first time a ticker is added.

> [!NOTE]
> The Tracker and Portfolio views require signing in. Without a Supabase project configured (see [Deploying to the Cloud](#deploying-to-the-cloud-vercel--render--supabase) below), the sign-in screen automatically falls back to **local accounts** — a real email/password account stored in your own local SQLite database, no cloud setup needed. Prefer not to make an account at all? Click **Continue as Guest** instead to try the full app with data kept only in your browser for that session.
>
> If you *do* configure `SUPABASE_JWKS_URL` to test real Supabase sign-in locally instead, `DATABASE_URL` stays independent of it — leave it unset and your account's portfolio/watchlist/price data lands in a local SQLite file, never touching production.

### Running Tests

```bash
make test       # backend test suite (pytest)
make coverage    # …with coverage (terminal summary + HTML report at htmlcov/index.html)
```

---

## Deploying to the Cloud (Vercel + Render + Supabase)

The hosted setup uses three free tiers: **Supabase** (Postgres + auth), **Render** (the FastAPI backend), and **Vercel** (the React frontend).

### 1. Supabase — database & authentication

1. Create a project at [supabase.com](https://supabase.com).
2. **Database URL:** Project Settings → Database → *Connection string* → **Session pooler**. Convert it to the asyncpg scheme:
   ```
   postgresql+asyncpg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```
3. **JWKS URL:** Project Settings → API → *JWT Keys* → *JWKS URL*. The backend uses this to verify user tokens against Supabase's published signing keys.
4. **Auth providers:** Authentication → Providers → enable **Email** (covers both magic links and password sign-in out of the box) and **Google** (follow Supabase's guide to create Google OAuth credentials). Under Authentication → URL Configuration, set the *Site URL* to your Vercel URL and add it to *Redirect URLs*.
5. **Password policy** (only matters if you use the password option): Authentication → Providers → Email → set *Minimum password length* and *Password requirements* to whatever this deployment should enforce (e.g. 8 chars, "Lowercase, uppercase letters, digits and symbols"). The frontend doesn't duplicate this policy — a signup that violates it is rejected by Supabase itself, and the UI just displays whatever message comes back, so it always matches whatever this setting currently is.

### 2. Render — the API

1. Push your fork to GitHub.
2. In Render, create a new **Web Service** from the repo.
   - **Root Directory:** leave as the repo root (the build context spans `utils/` and `backend/`).
   - **Runtime:** Docker, **Dockerfile Path:** [`docker/backend.Dockerfile`](docker/backend.Dockerfile). It runs `alembic upgrade head` automatically before starting the server.
   - **Health Check Path:** `/health`
3. Add the following environment variables:

   | Variable | Value |
   |----------|-------|
   | `DATABASE_URL` | the asyncpg pooler URL from step 1.2 |
   | `SUPABASE_JWKS_URL` | the JWKS URL from step 1.3 |
   | `CORS_ORIGINS` | your Vercel URL, e.g. `https://stakeout.vercel.app` |
   | `SUPABASE_SECRET_KEY` | Project Settings → API → API Keys → Secret keys (prefer this over the legacy `service_role` key — same access, individually revocable). Optional — only needed for "Delete account" to also remove the Supabase auth user. Full-access key: server-side only, never in the frontend. |

4. Deploy. The container entrypoint runs `alembic upgrade head` before starting the server, so tables are created automatically. Health check: `https://<your-service>.onrender.com/health`.

> [!NOTE]
> Render's free tier has an **ephemeral disk**, but that no longer matters for price data — the market_data table lives in Supabase alongside holdings, watchlists, and users, so it survives every deploy/restart. Free-tier services also sleep after inactivity; the first request after a sleep takes ~30 s.

### 3. Vercel — the frontend

1. Import the repo in Vercel and set the **Root Directory** to `frontend`.
2. Add environment variables:

   | Variable | Value |
   |----------|-------|
   | `VITE_API_URL` | your Render URL, e.g. `https://stakeout-api.onrender.com` |
   | `VITE_SUPABASE_URL` | Supabase Project Settings → API → Project URL |
   | `VITE_SUPABASE_ANON_KEY` | Supabase Project Settings → API → anon/public key |

3. Deploy. `vercel.json` already handles SPA routing.

Visitors who'd rather not create an account can still use the whole app via **Continue as Guest** on the sign-in screen — their watchlist and portfolio just stay in the browser instead of syncing to an account.

---

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_DIR` | `logs/` | Directory where log files are written |
| `LOG_LEVEL` | `DEBUG` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `ARCHIVE_START_DATE` | `2023-01-01` | Earliest date to archive stock data from |
| `STAKEOUT_DATA_DIR` | _(empty → repo root)_ | Root data directory override |
| `MODEL_DIR` | `model-store/` | Reserved for future ML model artifacts |
| `APP_NAME` | `Stakeout API` | Overrides the FastAPI app title shown in `/docs` |
| `DATABASE_URL` | _(empty → SQLite)_ | Postgres connection string for hosted mode |
| `SUPABASE_JWKS_URL` | _(empty → local accounts)_ | Verifies user sessions against Supabase's published signing keys — required for a hosted deployment; local dev falls back to local accounts or Guest Mode when unset |
| `SUPABASE_SECRET_KEY` | _(empty)_ | Lets "Delete account" also remove the Supabase auth user via the Admin API. Server-side only, never in the frontend |
| `CORS_ORIGINS` | _(empty)_ | Comma-separated allowed browser origins |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Where to reach [Ollama](https://ollama.com) for the optional AI Insight card / chat |
| `OLLAMA_MODEL` | `llama3.2:3b` | Ollama model used for AI explanations |

---

## Project Structure

```
stakeout/
├── docker-compose.yml             # Local/self-hosted stack: Postgres + API + frontend
├── docker/                        # Dockerfiles (backend + frontend) + nginx config; docker/backend.Dockerfile also used for the Render cloud deploy
├── Makefile                       # Common developer commands — run `make help` to list them
├── pyproject.toml                 # uv workspace and dependency config
├── .env.example                   # Environment variable template
│
├── utils/                         # Shared Python utilities (logging, helpers)
│
├── backend/                       # FastAPI REST API (auth, markets, news, FX, portfolio, watchlist, AI); fetches stock prices from Yahoo Finance into the market_data table
├── frontend/                      # React + TypeScript SPA (Vite, Tailwind, Recharts, Motion)
│
└── .github/
    └── workflows/ci.yml           # CI: runs the backend test suite on push/PR
```

---

## API Reference

The backend exposes a REST API (Swagger docs at **`/openapi`**). Endpoints marked 🔒 require an `Authorization: Bearer <supabase-jwt>` header — unauthenticated requests get a 401. Guest-mode sessions never call these directly; they're handled entirely client-side (see Features above).

**Stocks & market data**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | API health status and latency |
| `GET` | `/stocks/market?market=US\|IN` | Open/closed status for an exchange |
| `GET` | `/stocks/industries` · `/stocks/sectors` | Industry / sector → ticker groupings |
| `GET` | `/stocks/{ticker}?days=N` | Historical OHLCV data |
| `GET` | `/stocks/{ticker}/current` · `/intraday` | Live price / 15-min bars (market-hours aware per exchange) |
| `GET` | `/stocks/{ticker}/details` · `/eps` · `/revenue` · `/dashboard` | Analyst data and bundles |
| `GET` | `/stocks/indices` | Major US/India index quotes + 3-month sparkline series (cached 10 min) |
| `GET` | `/stocks/classification?tickers=A,B` | Batch sector/industry per ticker (cached 24 h) |

**AI** — optional, no auth; degrades to a 503 if [Ollama](https://ollama.com) isn't reachable

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/ai/stocks/{ticker}/explain?refresh=false` | Plain-English explanation of a stock's technicals + recent news (cached 1 h) |
| `POST` | `/ai/chat` | One turn of the floating AI chat, optionally aware of a stock or portfolio context |

**Watchlist** 🔒

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/watchlist/?market=US\|IN` | Your watchlist: `{ticker: {name, market}}` |
| `POST` | `/watchlist/{ticker}` | Add a ticker (also ensures its data archive exists) |
| `DELETE` | `/watchlist/{ticker}` | Remove from your watchlist (archive is kept — it's a shared cache) |

**Portfolio** 🔒

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/portfolio/?market=US\|IN` | Portfolio overview with P&L per holding |
| `GET` | `/portfolio/download?market=US\|IN` | Excel (.xlsx) export |
| `POST` | `/portfolio/{ticker}/buy` · `/sell` | Record transactions |
| `DELETE` | `/portfolio/{ticker}` · `/transactions/{id}` | Remove a holding / a transaction |

**Account** 🔒

| Method | Endpoint | Description |
|--------|----------|-------------|
| `DELETE` | `/account` | Permanently deletes your account and everything it owns (holdings, transactions, watchlist). Local accounts are removed directly; Supabase accounts also delete the auth user via the Admin API (needs `SUPABASE_SECRET_KEY`) |

**News & FX**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/news/market?region=all\|us\|in` | Market headlines (GDELT, Yahoo fallback; cached 15 min) |
| `GET` | `/news/stock/{ticker}` | Last 7 days of company → industry → sector → market headlines, newest first |
| `GET` | `/fx/USD/INR` | Daily reference exchange rate (cached 1 h) |

---

### Maintainer note — yfinance dependency

Market data is fetched via [yfinance](https://github.com/ranaroussi/yfinance), which works by scraping Yahoo Finance's internal endpoints. Yahoo does not publish an official public API, so **these endpoints can change without notice**, silently breaking data fetching. If users report missing or stale data and `/health` is fine, check whether a newer `yfinance` release patches the breakage, update it in [`backend/pyproject.toml`](backend/pyproject.toml), and redeploy. The same caution applies to GDELT (rate limits, occasional slow responses) — the news service degrades gracefully to Yahoo's per-ticker news feed.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, Uvicorn, SQLAlchemy (async), Alembic |
| Auth & DB | Supabase (Postgres, Google OAuth, magic links), PyJWT |
| Data | yfinance, pandas, pandas-market-calendars, GDELT, Frankfurter, Ollama (optional AI layer) |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Recharts, Motion, React Router |
| Deploy | uv, Docker Compose (self-hosted), Render, Vercel |
| CI/CD | GitHub Actions |

---

## License

[MIT](LICENSE) — free to use, modify, and distribute. See the `LICENSE` file for the full text.
