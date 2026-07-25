
.PHONY: install sync \
        backend frontend dashboard \
        test coverage \
        docker-up docker-down docker-logs docker-reset

# ── Environment ──────────────────────────────────────────────────────────────

install:
	uv sync

sync: install

# ── Dashboard ─────────────────────────────────────────────────────────────────

backend:
	cd backend/src && uv run uvicorn main:app --reload

frontend:
	cd frontend && npm run dev

# ── Docker (local / self-hosted) ─────────────────────────────────────────────

docker-up:
	docker compose up --build -d
	@echo "Stakeout is starting at http://localhost:3000"

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# Removes containers AND the Postgres volume (wipes local accounts/portfolios)
docker-reset:
	docker compose down -v

# ── Tests ─────────────────────────────────────────────────────────────────────

test:
	uv run --group dev pytest -v

coverage:
	uv run --group dev pytest --cov=backend/src --cov-report=term-missing --cov-report=html
	@echo "HTML report: htmlcov/index.html"
