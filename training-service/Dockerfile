# ── Stage 1: build deps ───────────────────────────────────────────────────────
# python:3.11-slim is ~50MB vs ~900MB for the full image.
# We use a separate builder stage so that gcc/build tools don't end up
# in the final image — they're only needed to compile numpy/scipy wheels.
FROM python:3.11-slim AS builder

WORKDIR /app

# gcc + libgomp are needed to compile some sklearn/numpy C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install into a prefix directory we can COPY cleanly into the runtime stage.
# --no-cache-dir keeps the image smaller (no pip HTTP cache stored in layer).
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# libgomp1 is needed at runtime by sklearn (OpenMP for parallel jobs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder — no build tools come along
COPY --from=builder /install /usr/local

# Copy application code
COPY app.py db.py pipeline.py schemas.py ./

# ── Non-root user ──────────────────────────────────────────────────────────────
# Running as root inside a container is bad practice — if there's an RCE vuln
# in your app, the attacker gets root on the container (and potentially the host
# if Docker is misconfigured). A dedicated user limits blast radius.
RUN useradd --no-create-home --shell /bin/false appuser
USER appuser

EXPOSE 8001

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]