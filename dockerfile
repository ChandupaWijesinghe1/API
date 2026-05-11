# syntax=docker/dockerfile:1
#
# Multi-stage build — why it matters
# ---------------------------------
# Stage 1 can include compilers and extra tooling; Stage 2 keeps only what runs the app.
# That shrinks the final image, speeds deploys, and reduces attack surface (no build tools in prod).
#
# Compare image sizes (after building both):
#   docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | findstr /i "api"
# Build this image:     docker build -t api:multi -f dockerfile .
# Naive single-stage:   docker build -t api:single -f Dockerfile.single .
# (Create Dockerfile.single only for the lab: one FROM, apt + venv + same pip install + COPY src — no second stage.)

# -----------------------------------------------------------------------------
# Stage 1 (builder): create a venv and install dependencies there
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS builder
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir fastapi uvicorn pydantic sqlalchemy psycopg2-binary

# -----------------------------------------------------------------------------
# Stage 2 (runtime): only base image + venv + application code (no build chain)
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PATH="/venv/bin:$PATH"

COPY --from=builder /venv /venv
COPY src ./src

# Listen on all interfaces inside the container; map host → container: docker run -p 8000:8000
# Then open http://127.0.0.1:8000/health on the host
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
