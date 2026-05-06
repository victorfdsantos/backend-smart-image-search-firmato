# =============================================================================
# Build stage
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir \
        torch==2.5.1 \
        --index-url https://download.pytorch.org/whl/cu124 && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# =============================================================================
# Runtime stage
# =============================================================================
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libjpeg62-turbo \
    libpng16-16 \
    libwebp7 \
    libglib2.0-0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY src/ ./src/

RUN useradd --no-create-home --shell /bin/false --home-dir /app appuser && \
    mkdir -p /app/.cache/huggingface && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9000/health')"

CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "9000", \
     "--workers", "1", \
     "--log-level", "info", \
     "--no-access-log"]