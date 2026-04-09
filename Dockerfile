# ─── Base Stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps for lxml / Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── App Stage ───────────────────────────────────────────────────────────────
FROM base AS app

COPY . .

RUN mkdir -p /app/data /app/downloads

RUN adduser --disabled-password --gecos "" botuser && \
    chown -R botuser:botuser /app
USER botuser

# Render free tier uses port 10000 by default
EXPOSE 10000

CMD ["python", "main.py"]
