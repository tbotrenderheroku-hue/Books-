# ─── Build Stage ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# Prevent .pyc files and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System dependencies for lxml, Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── App Stage ───────────────────────────────────────────────────────────────
FROM base AS app

COPY . .

# Create data directory for database
RUN mkdir -p /app/data /app/downloads

# Non-root user for security
RUN adduser --disabled-password --gecos "" botuser && \
    chown -R botuser:botuser /app
USER botuser

EXPOSE 8443

CMD ["python", "main.py"]
