# ─── Stage 1: Frontend build ──────────────────────────────────────────────────
FROM debian:12-slim AS frontend-builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV MISE_DATA_DIR="/mise"
ENV MISE_CONFIG_DIR="/mise"
ENV MISE_CACHE_DIR="/mise/cache"
ENV MISE_INSTALL_PATH="/usr/local/bin/mise"
ENV PATH="/mise/shims:$PATH"
ENV MISE_YES=1

RUN curl https://mise.run | sh

WORKDIR /app

# Install node via mise
COPY mise.toml ./
RUN mise trust && mise install node

# Install frontend deps
COPY frontend/package*.json ./frontend/
RUN mise exec -- sh -c "cd frontend && npm ci"

# Build frontend
COPY frontend/ ./frontend/
RUN mise exec -- sh -c "cd frontend && npm run build"


# ─── Stage 2: Production image ────────────────────────────────────────────────
FROM debian:12-slim AS production

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl ca-certificates build-essential git \
    && rm -rf /var/lib/apt/lists/*

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV MISE_DATA_DIR="/mise"
ENV MISE_CONFIG_DIR="/mise"
ENV MISE_CACHE_DIR="/mise/cache"
ENV MISE_INSTALL_PATH="/usr/local/bin/mise"
ENV PATH="/mise/shims:$PATH"
ENV MISE_YES=1

RUN curl https://mise.run | sh

WORKDIR /app

# Install python + uv via mise
COPY mise.toml ./
RUN mise trust && mise install python uv

# Install Python dependencies (production only)
COPY pyproject.toml uv.lock* ./
RUN mise exec -- uv sync --no-dev

# Copy application source
COPY backend/ ./backend/
COPY plugins/ ./plugins/
COPY templates/ ./templates/

# Copy built frontend from stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Runtime data directories
RUN mkdir -p data/logs data/audit data/secrets

EXPOSE 8000

CMD ["mise", "exec", "--", "uv", "run", "uvicorn", "backend.app.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
