# Market Lens

**A free, open-source desktop app for monitoring stock market trends.**

[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-3b82f6)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-20%2B-84cc16)](https://nodejs.org/)
[![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-8b5cf6)]()

---

## What Is Market Lens?

Market Lens is a free, open-source desktop application built for everyday people who want to keep an eye on their stocks — without paying for a Bloomberg terminal or a SaaS subscription.

You get a clean dashboard with price charts, volume data, analyst insights, earnings history, and peer comparison tools, all powered by publicly available market data. No account required. No cloud sync. No ads.

You're also encouraged to fork this project and build your own version. The codebase is intentionally approachable — a Python backend, a React frontend, and a single-command build that packages everything into one executable.

> [!WARNING]
> **Not financial advice.** Market Lens is for informational and educational purposes only. Nothing displayed in this application constitutes financial, investment, or trading advice. Always do your own research and consult a qualified financial professional before making any investment decisions.
>
> **Data source disclaimer.** All market data is fetched via [yfinance](https://github.com/ranaroussi/yfinance), an open-source library that retrieves data from Yahoo Finance. This data may be delayed, incomplete, or inaccurate. Use of Yahoo Finance data is subject to [Yahoo Finance's Terms of Service](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) and is intended for personal, non-commercial use only. Do not use this application or its data for commercial purposes.

---

## Features

- **Interactive Price & Volume Charts** — view any tracked stock from 1-day intraday all the way back to 3 years, with OHLCV tooltips and dynamic coloring (green/red)
- **Live Price Updates** — current price refreshes every 2 minutes while the market is open; pre-market and after-hours data shown with timezone info
- **OHLCV Stats Block** — Open, High, Low, Close, Volume and day change (%) in one glance
- **Analyst Price Targets** — visual range bar showing low/high/mean/median targets vs. current price, with upside % calculated
- **Analyst Recommendations** — stacked breakdown of Strong Buy → Strong Sell across up to 4 recent periods
- **EPS & Revenue Estimates** — tables with analyst consensus and growth % for upcoming quarters
- **Earnings & Revenue History** — bar charts with toggles for Growth %, Surprise %, and Actual values
- **Peer Comparison** — normalized % change chart to compare stocks in the same industry or sector side-by-side
- **Watchlist Management** — add and remove tickers from your personal list; stocks are organized by industry and sector tabs
- **Portfolio Tracker** — log buy and sell transactions with FIFO cost-basis, track unrealized and realized P&L per holding, and export your full portfolio to Excel
- **Health Dashboard** — monitor API latency with a rolling history chart so you know when data is stale

---

## Using the Latest Release

No Python or Node required — just download and run.

**1. Go to the [Releases page](https://github.com/vdudhaiy/market-lens/releases/latest) and download the binary for your OS:**

| OS | File |
|----|------|
| Windows | `market-lens-windows.exe` |
| macOS | `market-lens-macos` |
| Linux | `market-lens-linux` |

**2. Run it:**

### Windows

Because Market Lens is not code-signed (code certificates cost money and this is a free project), Windows SmartScreen will show a warning the first time you run it. Here's how to proceed:

1. Double-click `market-lens-windows.exe`
2. If you see **"Windows protected your PC"**, click **More info**
3. Click **Run anyway**

The source code is fully open — you can audit every line before running it.

### macOS

macOS Gatekeeper will quarantine the downloaded binary. Remove the quarantine attribute and make it executable:

```bash
xattr -d com.apple.quarantine market-lens-macos
chmod +x market-lens-macos
./market-lens-macos
```

### Linux

```bash
chmod +x market-lens-linux
./market-lens-linux
```

**3. The app starts a local server and automatically opens your default browser at `http://127.0.0.1:8000`.**

Stock data is stored in a `market-lens-data/` folder next to the executable — portable and fully local.

---

## Quick Start — Development Setup

### Prerequisites

- [Python 3.12+](https://www.python.org/downloads/)
- [Node.js 20+](https://nodejs.org/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/vdudhaiy/market-lens.git
cd market-lens

# 2. Install Python dependencies
make install           # equivalent to: uv sync

# 3. Install frontend dependencies
cd packages/dashboard/frontend
npm install
cd ../../..

# 4. Set up environment variables
cp .env.example .env   # then edit .env as needed

# 5. Fetch initial stock data (downloads from Yahoo Finance)
make pipeline

# 6. Start the backend server (Terminal 1)
make backend           # FastAPI at http://127.0.0.1:8000

# 7. Start the frontend dev server (Terminal 2)
make frontend          # React at http://localhost:5173
```

Open **http://localhost:5173** in your browser.

---

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_DIR` | `logs/` | Directory where log files are written |
| `LOG_LEVEL` | `DEBUG` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `ARCHIVE_DATA_DIR` | `data/archive_stock_data/` | Where historical CSV files are stored |
| `ARCHIVE_START_DATE` | `2023-01-01` | Earliest date to archive stock data from |
| `MARKET_LENS_DATA_DIR` | _(empty)_ | Root data directory; set automatically by the packaged executable — leave empty in development |
| `MODEL_DIR` | `model-store/` | Reserved for future ML model artifacts |

---

## Project Structure

```
market-lens/
├── launcher.py                    # Entry point for the packaged executable
├── market-lens.spec               # PyInstaller build specification
├── Makefile                       # Common developer commands
├── pyproject.toml                 # uv workspace and dependency config
├── .env.example                   # Environment variable template
│
├── utils/                         # Shared Python utilities (logging, helpers)
│
├── packages/
│   ├── pipeline/                  # Data pipeline — fetches and archives stock CSVs via Yahoo Finance
│   └── dashboard/
│       ├── backend/               # FastAPI REST API (also serves the built frontend)
│       └── frontend/              # React + TypeScript SPA (Vite, Tailwind CSS, Recharts)
│
└── .github/
    └── workflows/release.yml      # CI: cross-builds Windows / macOS / Linux executables on tag push
```

> `packages/models/` is a placeholder reserved for a future ML module and is not yet implemented.

---

## Building from Source

```bash
make release
```

This runs three steps in sequence:

1. `npm run build` — compiles the React frontend into `packages/dashboard/backend/frontend-dist/`
2. `pip install pyinstaller` — installs the bundler
3. `pyinstaller market-lens.spec` — outputs a single executable to `dist/`

To trigger a multi-platform release via GitHub Actions, push a version tag:

```bash
git tag v1.0.0
git push --tags
```

The workflow builds `market-lens-windows.exe`, `market-lens-macos`, and `market-lens-linux` automatically and attaches them to a GitHub Release.

---

## API Reference

The backend exposes a REST API at `http://127.0.0.1:8000`. Interactive Swagger docs are available at **`/openapi`** when the server is running.

**Stocks**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | API health status and latency |
| `GET` | `/stocks/` | List all tracked stocks |
| `GET` | `/stocks/market` | Current market open/closed status |
| `GET` | `/stocks/industries` | Industry → ticker groupings |
| `GET` | `/stocks/sectors` | Sector → ticker groupings |
| `POST` | `/stocks/{ticker}` | Add a stock to the watchlist |
| `DELETE` | `/stocks/{ticker}` | Remove a stock from the watchlist |
| `GET` | `/stocks/{ticker}?days=N` | Historical OHLCV data for N days |
| `GET` | `/stocks/{ticker}/current` | Live current price |
| `GET` | `/stocks/{ticker}/intraday` | 15-minute intraday bars (used for 1D view) |
| `GET` | `/stocks/{ticker}/details` | Analyst targets, recommendations, EPS/revenue estimates |
| `GET` | `/stocks/{ticker}/eps` | EPS history (last 4 quarters) |
| `GET` | `/stocks/{ticker}/revenue` | Revenue history (last 4 quarters) |
| `GET` | `/stocks/{ticker}/dashboard` | All dashboard data for a ticker in one request |

**Portfolio**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/portfolio/` | Full portfolio overview with P&L per holding |
| `GET` | `/portfolio/download` | Download portfolio as an Excel (.xlsx) file |
| `GET` | `/portfolio/{ticker}` | Holding details for a single ticker |
| `POST` | `/portfolio/{ticker}/buy` | Record a buy transaction (`shares`, `bought_at`, optional `date`) |
| `POST` | `/portfolio/{ticker}/sell` | Record a sell transaction (`shares`, `sold_at`, optional `date`) |
| `DELETE` | `/portfolio/{ticker}/transactions/{id}` | Delete a specific transaction |
| `DELETE` | `/portfolio/{ticker}` | Remove a holding and all its transactions |

All market data is sourced from [Yahoo Finance](https://finance.yahoo.com/) via the `yfinance` library.

---

## Make It Your Own

Market Lens is designed to be forked. Here are some directions you might take it:

- Add new data sources beyond Yahoo Finance
- Build out the `packages/models/` ML module for price prediction
- Create custom alert rules for price thresholds or analyst rating changes
- Package it as a proper Electron app with a native menu bar

To contribute back:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Open a pull request

### Maintainer note — yfinance dependency

Market data is fetched via [yfinance](https://github.com/ranaroussi/yfinance), an open-source library that works by scraping Yahoo Finance's internal endpoints. Yahoo Finance does not publish an official public API, so **these endpoints can change without notice**, silently breaking data fetching.

If users report missing or stale data and the app itself is healthy (check `/health`), the first thing to investigate is whether a newer version of `yfinance` has been released that patches the breakage. Update it in [`packages/pipeline/pyproject.toml`](packages/pipeline/pyproject.toml) and cut a new release.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Data | yfinance, pandas, pandas-market-calendars |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Recharts |
| Packaging | PyInstaller, uv |
| CI/CD | GitHub Actions |

---

## License

[MIT](LICENSE) — free to use, modify, and distribute. See the `LICENSE` file for the full text.
