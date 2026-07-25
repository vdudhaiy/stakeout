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