# ── Stage 1: Build Frontend Assets ────────────────────────────────────
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend

COPY src/frontend/package*.json ./
RUN npm ci

COPY src/frontend/ ./
RUN chmod -R +x node_modules/.bin || true
RUN npm run build

# ── Stage 2: Runtime Container ────────────────────────────────────────
FROM python:3.13-slim AS runner

WORKDIR /app

# Install system dependencies including curl and Microsoft ODBC 18 driver for SQL Server / Fabric DB
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    unixodbc \
    unixodbc-dev \
    ca-certificates \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reliable Python package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency specifications and install runtime packages
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy backend application and source code
COPY src/ ./src/

# Copy compiled frontend distribution from Stage 1 into the location expected by relay.py
COPY --from=frontend-builder /app/frontend/dist ./src/frontend/dist

# Expose port for FastAPI / WebSockets
EXPOSE 8000

ENV HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1

# Run FastAPI app using the uv virtual environment
CMD ["/app/.venv/bin/uvicorn", "src.backend.relay:app", "--host", "0.0.0.0", "--port", "8000"]
