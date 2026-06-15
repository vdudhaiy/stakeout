'''
Configuration for the Market Lens Dashboard backend, including environment variable loading and constants.
'''
import os
from pathlib import Path


def _base_dir() -> Path:
    # When running as a packaged executable, MARKET_LENS_DATA_DIR points to the
    # writable data folder next to the binary. In dev mode it is not set, so we
    # fall back to the repo root (parents[5] of this file).
    override = os.getenv("MARKET_LENS_DATA_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[5]


_BASE = _base_dir()

BASE_DIR = _BASE

ARCHIVE_DATA_DIR = _BASE / os.getenv("ARCHIVE_DATA_DIR", "data/archive_stock_data/")

MODEL_DIR = _BASE / os.getenv("MODEL_DIR", "model-store/")