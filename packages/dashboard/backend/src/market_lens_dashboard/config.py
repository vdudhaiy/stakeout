'''
Configuration for the Market Lens Dashboard backend, including environment variable loading and constants.
'''
import os
import sys
from pathlib import Path


def _base_dir() -> Path:
    override = os.getenv("MARKET_LENS_DATA_DIR")
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    if hasattr(sys, "_MEIPASS"):
        # Running as a packaged executable — store user data in the platform-
        # appropriate location rather than next to the binary (which may not be
        # writable, e.g. under Program Files on Windows).
        # Windows: %LOCALAPPDATA%\MarketLens
        # macOS:   ~/Library/Application Support/MarketLens
        # Linux:   ~/.local/share/MarketLens  (respects $XDG_DATA_HOME)
        from platformdirs import user_data_dir
        path = Path(user_data_dir("MarketLens", appauthor=False))
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path(__file__).resolve().parents[5]  # dev: repo root


_BASE = _base_dir()

BASE_DIR = _BASE

ARCHIVE_DATA_DIR = _BASE / os.getenv("ARCHIVE_DATA_DIR", "data/archive_stock_data/")
ARCHIVE_DATA_DIR.mkdir(parents=True, exist_ok=True)

MODEL_DIR = _BASE / os.getenv("MODEL_DIR", "model-store/")