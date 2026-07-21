
.PHONY: install sync \
        backend frontend dashboard \
        test coverage

# ── Environment ──────────────────────────────────────────────────────────────

install:
	uv sync

sync: install

# ── Dashboard ─────────────────────────────────────────────────────────────────

backend:
	cd backend/src && uv run uvicorn market_lens_dashboard.main:app --reload

frontend:
	cd frontend && npm run dev

# ── Tests ─────────────────────────────────────────────────────────────────────

test:
	uv run --group dev pytest -v

coverage:
	uv run --group dev pytest --cov=market_lens_dashboard --cov-report=term-missing --cov-report=html
	@echo "HTML report: htmlcov/index.html"
