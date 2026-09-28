# Multi-Stage Production Dockerfile for AI Bank Statement Parser Micro-SaaS

# Stage 1: Build the React Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Production Python Backend + Static Asset Server
FROM python:3.12-slim

# Install system utilities & OpenCV headless prerequisites
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast Python dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency specifications
COPY backend/pyproject.toml backend/uv.lock* ./backend/

# Install Python production dependencies
WORKDIR /app/backend
RUN uv sync --frozen --no-dev --no-install-project

# Copy backend application source code
COPY backend/app ./app

# Copy built frontend assets from Stage 1 into the location expected by FastAPI main.py
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Create storage upload directory
RUN mkdir -p /app/backend/storage/uploads

# Expose server port
ENV PORT=8000
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:${PORT}/api/health || exit 1

# Launch production Uvicorn server
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
