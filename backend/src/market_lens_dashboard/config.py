'''
Configuration for the Market Lens Dashboard backend, including environment variable loading and constants.
'''
import os
from pathlib import Path


def _base_dir() -> Path:
    override = os.getenv("MARKET_LENS_DATA_DIR")
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path(__file__).resolve().parents[3]  # dev: repo root


_BASE = _base_dir()

BASE_DIR = _BASE

MODEL_DIR = _BASE / os.getenv("MODEL_DIR", "model-store/")