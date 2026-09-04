# ============================================================
# Backend Dockerfile — The Lenny Growth Assistant
# Optimized Python container for FastAPI backend
# ============================================================

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend \
    HOME=/root \
    HF_HOME=/tmp/huggingface \
    TRANSFORMERS_CACHE=/tmp/huggingface \
    TORCH_HOME=/tmp/torch

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /app/backend/requirements.txt

# Copy backend application source code
COPY backend /app/backend

WORKDIR /app/backend

# Create writable cache directory
RUN mkdir -p /tmp/huggingface /tmp/torch && chmod -R 777 /tmp

EXPOSE 8000

# Container healthcheck probing the deep health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Automatically ingest sample transcripts on boot before starting the server
# (Idempotent: skips if already ingested; if DB is temporarily unreachable, continues to uvicorn)
CMD ["sh", "-c", "python scripts/ingest.py --source sample || true; exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
