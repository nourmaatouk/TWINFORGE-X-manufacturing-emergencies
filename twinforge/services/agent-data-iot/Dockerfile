# ═══════════════════════════════════════════════════════════════
# Agent 3: Data/IoT Executor — Dockerfile
# ═══════════════════════════════════════════════════════════════

FROM python:3.11-slim AS base

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# ── Install system dependencies ─────────────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# ── Install Python dependencies ─────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy service code ───────────────────────────────────────
COPY app/ /app/app/

# ── Create non-root user ────────────────────────────────────
RUN useradd --create-home --shell /bin/bash agent && \
    chown -R agent:agent /app
USER agent

# ── Expose port ─────────────────────────────────────────────
EXPOSE 8003

# ── Health check ────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

# ── Entrypoint ──────────────────────────────────────────────
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003", "--workers", "1"]
