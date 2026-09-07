'''
Configuration for the Stakeout backend, including environment variable loading and constants.
'''
import os
from pathlib import Path


def _base_dir() -> Path:
    override = os.getenv("STAKEOUT_DATA_DIR")
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path(__file__).resolve().parents[2]  # dev: repo root


_BASE = _base_dir()

BASE_DIR = _BASE

MODEL_DIR = _BASE / os.getenv("MODEL_DIR", "model-store/")

# AI Explanation Layer: talks to a locally-run Ollama instance. Optional —
# services/llm_service.py degrades to returning None (never raises) when
# Ollama isn't reachable, so the rest of the app is unaffected.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

# Background price-archive sweep (see services/stock_service.refresh_all_archives).
# Minutes between passes; 0 disables it entirely. The default is deliberately
# short relative to the host's idle spin-down — on a free tier the process is
# recycled often enough that the startup pass is what actually keeps the
# archive current, and the loop only matters for a long-lived instance.
ARCHIVE_SWEEP_INTERVAL_MINUTES = int(os.getenv("ARCHIVE_SWEEP_INTERVAL_MINUTES", "60"))

# Seconds to wait before the first sweep, so a user's own page load isn't
# competing with it for the upstream budget the moment the process wakes.
ARCHIVE_SWEEP_START_DELAY_SECONDS = float(os.getenv("ARCHIVE_SWEEP_START_DELAY_SECONDS", "45"))

# Gap between tickers within a sweep. A burst of simultaneous history
# downloads is the exact shape yfinance rate-limits, and this job has no
# deadline — nobody is waiting on it.
ARCHIVE_SWEEP_SPACING_SECONDS = float(os.getenv("ARCHIVE_SWEEP_SPACING_SECONDS", "10"))

# Most tickers to actually download in one pass. A host that spins down
# runs the startup pass on every wake, so an uncapped sweep is not
# occasional maintenance — it is a burst of history downloads each time
# somebody visits, competing with their own requests for the same
# upstream budget. Capping spreads a cold archive over several passes.
ARCHIVE_SWEEP_MAX_PER_PASS = int(os.getenv("ARCHIVE_SWEEP_MAX_PER_PASS", "8"))

# Company peers (services/peers_service.py) and any other Finnhub lookups.
# Optional — peers_service degrades to an empty list (never raises) when
# unset, same spirit as OLLAMA_BASE_URL above.
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")