# Stakeout

**Open markets, open source.**

A free, open-source stock tracker for US and Indian markets, deployed to the cloud with multi-user accounts.

[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-3b82f6)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-20%2B-84cc16)](https://nodejs.org/)
[![Platforms](https://img.shields.io/badge/platforms-Web-8b5cf6)]()

---

## What Is Stakeout?

Stakeout is a free, open-source app built for everyday people who want to keep watch on their stakes in the market — without paying for a Bloomberg terminal or a SaaS subscription.

You get a clean dashboard with price charts, technical indicators, analyst insights, earnings history, layered news headlines, peer comparison, and a two-market portfolio tracker (US and India) with FIFO cost basis — all powered by publicly available data.

Deploy the codebase to Vercel + Render + Supabase and get Google / email sign-in with per-user watchlists and portfolios. Don't want an account? Guest Mode lets anyone try the full app with nothing saved beyond their browser session.

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
- **Layered news** — the home page shows US and India market headlines; each stock's dashboard shows company → industry → market news, all clickable through to the source.
- **Live price updates** — refreshes every 2 minutes while that stock's home exchange is open; pre-market data shown with timezone info.
- **Analyst insights** — price target range bar with upside %, recommendation drift (Strong Buy → Strong Sell), and EPS/revenue estimates for upcoming quarters.
- **Earnings & revenue history** — bar charts with Growth %, Surprise %, and Actual toggles.
- **Peer comparison** — normalized % change chart to compare stocks in the same industry or sector.
- **Portfolio tracker** — FIFO cost basis, unrealized/realized P&L per holding, allocation donut, and one-click Excel export — per market.
- **Watchlist with market filter** — organize by industry/sector tabs, filter All / US / India; a ticker-tape marquee streams your watchlist's latest prices under the navbar.
- **Multi-user accounts** — Google OAuth or email magic-link sign-in via Supabase; each user gets their own watchlist and portfolios. **Guest Mode** lets anyone try the app without signing in — watchlist and portfolio data stay in the browser for that session and are never written to the database.
- **Dual market status pill** — NYSE and NSE open/closed at a glance, with session times in ET/IST and your local timezone.
- **Backend health monitor, dark/light themes, caching** — API latency pill with history; a paper-ledger light theme and terminal-dark theme; TTL caches for quotes (60 s), news (15 min), and FX (1 h) to stay well within free-tier data source limits.

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
> The Dashboard and Portfolio views require signing in. Without a Supabase project configured (see [Deploying to the Cloud](#deploying-to-the-cloud-vercel--render--supabase) below), the sign-in screen automatically falls back to **local accounts** — a real email/password account stored in your own local SQLite database, no cloud setup needed. Prefer not to make an account at all? Click **Continue as Guest** instead to try the full app with data kept only in your browser for that session.
>
> If you *do* configure `SUPABASE_JWKS_URL` to test real Supabase sign-in locally instead, `DATABASE_URL` stays independent of it — leave it unset and your account's portfolio/watchlist/price data lands in a local SQLite file, never touching production.

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
4. **Auth providers:** Authentication → Providers → enable **Email** (magic links work out of the box) and **Google** (follow Supabase's guide to create Google OAuth credentials). Under Authentication → URL Configuration, set the *Site URL* to your Vercel URL and add it to *Redirect URLs*.

### 2. Render — the API

1. Push your fork to GitHub.
2. In Render, create a **Blueprint** from the repo — it picks up [`render.yaml`](render.yaml) automatically.
3. Fill in the environment variables when prompted:

   | Variable | Value |
   |----------|-------|
   | `DATABASE_URL` | the asyncpg pooler URL from step 1.2 |
   | `SUPABASE_JWKS_URL` | the JWKS URL from step 1.3 |
   | `CORS_ORIGINS` | your Vercel URL, e.g. `https://stakeout.vercel.app` |

4. Deploy. The pre-deploy hook runs `alembic upgrade head` to create tables. Health check: `https://<your-service>.onrender.com/health`.

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
| `MARKET_LENS_DATA_DIR` | _(empty → repo root)_ | Root data directory override |
| `MODEL_DIR` | `model-store/` | Reserved for future ML model artifacts |
| `DATABASE_URL` | _(empty → SQLite)_ | Postgres connection string for hosted mode |
| `SUPABASE_JWKS_URL` | **required** | Verifies user sessions against Supabase's published signing keys |
| `CORS_ORIGINS` | _(empty)_ | Comma-separated allowed browser origins |

---

## Project Structure

```
stakeout/
├── render.yaml                    # Render blueprint (hosted backend)
├── Makefile                       # Common developer commands
├── pyproject.toml                 # uv workspace and dependency config
├── .env.example                   # Environment variable template
│
├── utils/                         # Shared Python utilities (logging, helpers)
│
├── backend/                       # FastAPI REST API (auth, markets, news, FX, portfolio, watchlist); fetches stock prices from Yahoo Finance into the market_data table
├── frontend/                      # React + TypeScript SPA (Vite, Tailwind, Recharts, Framer Motion)
│
└── .github/
    └── workflows/ci.yml           # CI: runs the backend test suite on push/PR
```

> **Why do the Python packages still say `market_lens`?** The internal package name (`market_lens_dashboard`) was deliberately kept when the app was rebranded — renaming it would break every import, the uv workspace config, and existing data directories, for zero user-facing benefit. Only the branding you see is Stakeout.

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

**News & FX**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/news/market?region=all\|us\|in` | Market headlines (GDELT, Yahoo fallback; cached 15 min) |
| `GET` | `/news/stock/{ticker}` | Layered company → industry → market headlines |
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
| Data | yfinance, pandas, pandas-market-calendars, GDELT, Frankfurter |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Recharts, Framer Motion, React Router |
| Deploy | uv, Render, Vercel |
| CI/CD | GitHub Actions |

---

## License

[MIT](LICENSE) — free to use, modify, and distribute. See the `LICENSE` file for the full text.
