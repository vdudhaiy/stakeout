# Stakeout API — FastAPI backend.
# Build context is the repo root (the uv workspace spans /, utils/, backend/).
#   docker compose build backend
FROM python:3.12-slim AS runtime

# uv: fast, lockfile-driven installs identical to local `make install`
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Layer-cache dependencies: metadata + lockfile first, source after.
COPY pyproject.toml uv.lock ./
COPY utils/pyproject.toml utils/pyproject.toml
COPY backend/pyproject.toml backend/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-workspace

# Workspace source
COPY utils/ utils/
COPY backend/ backend/
RUN uv sync --frozen --no-dev

# Writable data dir for logs etc. (config.STAKEOUT_DATA_DIR)
RUN mkdir -p /data
ENV STAKEOUT_DATA_DIR=/data

EXPOSE 8000

# Apply migrations, then serve. DATABASE_URL comes from docker-compose.yml.
# alembic.ini resolves script/source paths via %(here)s, so -c is enough.
CMD ["sh", "-c", "uv run --frozen --no-dev alembic -c backend/alembic.ini upgrade head && uv run --frozen --no-dev uvicorn main:app --host 0.0.0.0 --port 8000"]
