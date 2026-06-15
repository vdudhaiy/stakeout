# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for market-lens.
#
# Before running PyInstaller, build the frontend first:
#   cd packages/dashboard/frontend && npm run build
#
# Then from the repo root:
#   pyinstaller market-lens.spec
#
# Output: dist/market-lens  (or dist/market-lens.exe on Windows)

import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

# ---------------------------------------------------------------------------
# Verify the frontend has been built
# ---------------------------------------------------------------------------
FRONTEND_DIST = "packages/dashboard/frontend/dist"
if not os.path.isdir(FRONTEND_DIST):
    raise SystemExit(
        f"\n[market-lens.spec] Frontend dist not found at '{FRONTEND_DIST}'.\n"
        "Run the following first:\n"
        "  cd packages/dashboard/frontend && npm run build\n"
    )

# ---------------------------------------------------------------------------
# Collect data / binaries / hidden-imports for packages that use dynamic
# loading or C-extensions that PyInstaller can't detect automatically.
# ---------------------------------------------------------------------------
def _collect(*packages):
    all_datas, all_bins, all_hidden = [], [], []
    for pkg in packages:
        d, b, h = collect_all(pkg)
        all_datas.extend(d)
        all_bins.extend(b)
        all_hidden.extend(h)
    return all_datas, all_bins, all_hidden

collected_datas, collected_bins, collected_hidden = _collect(
    "pandas",
    "pandas_market_calendars",
    "yfinance",
    "sqlalchemy",
    "aiosqlite",
    "lxml",
    "uvicorn",
    "fastapi",
    "starlette",
    "pydantic",
    "pydantic_settings",
    "anyio",
    "h11",
    "httptools",
    "websockets",
)

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    ["launcher.py"],
    # Add src directories so PyInstaller finds workspace packages even if
    # editable-install .pth files are not picked up automatically.
    pathex=[
        "packages/dashboard/backend/src",
        "packages/pipeline/src",
        "utils/src",
    ],
    binaries=collected_bins,
    datas=[
        # Bundle the built React frontend under frontend-dist/ in _MEIPASS
        (FRONTEND_DIST, "frontend-dist"),
        *collected_datas,
    ],
    hiddenimports=[
        # Workspace packages (dynamically imported inside service functions)
        "market_lens_dashboard",
        "market_lens_dashboard.main",
        "market_lens_dashboard.config",
        "market_lens_dashboard.database",
        "market_lens_dashboard.routers",
        "market_lens_dashboard.routers.stocks",
        "market_lens_dashboard.routers.health",
        "market_lens_dashboard.routers.portfolio",
        "market_lens_dashboard.services",
        "market_lens_dashboard.services.stock_service",
        "market_lens_dashboard.services.portfolio_service",
        "market_lens_dashboard.schemas",
        "market_lens_dashboard.schemas.stocks",
        "market_lens_dashboard.schemas.portfolio",
        "market_lens_dashboard.models",
        "market_lens_dashboard.models.portfolio",
        "market_lens_pipeline",
        "market_lens_pipeline.fetchers",
        "market_lens_pipeline.fetchers.price",
        "market_lens_pipeline.tickers",
        "market_lens_pipeline.processors",
        "market_lens_pipeline.processors.features",
        "market_lens_pipeline.pipeline",
        "market_lens_utils",
        "market_lens_utils.logs",
        # SQLAlchemy async + dialects loaded at runtime via URL scheme
        "aiosqlite",
        "sqlalchemy.ext.asyncio",
        "sqlalchemy.dialects.sqlite",
        "sqlalchemy.dialects.sqlite.aiosqlite",
        "sqlalchemy.dialects.postgresql",
        *collected_hidden,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Reduce bundle size by excluding large packages not used at runtime
        "matplotlib",
        "IPython",
        "jupyter",
        "notebook",
        "sklearn",
        "scipy",
        "tensorflow",
        "torch",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="market-lens",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # console=True shows the terminal window (useful while testing).
    # Set to False once you are happy with the build for a cleaner UX.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
