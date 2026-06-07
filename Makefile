
.PHONY: install sync \
        fetch-price fetch-data update-price process-data \
        pipeline

# ── Environment ──────────────────────────────────────────────────────────────

install:
	uv sync

sync: install

# ── Pipeline ─────────────────────────────────────────────────────────────────

fetch-price:
	uv run pipeline --fetch-price

fetch-data:
	uv run pipeline --fetch-data

update-price:
	uv run pipeline --update-price

process-data:
	uv run pipeline --process-data

pipeline:
	uv run pipeline
