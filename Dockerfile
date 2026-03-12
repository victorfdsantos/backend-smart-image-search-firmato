# =============================================================================
# Build stage — instala dependências pesadas uma vez só
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /build

# Dependências de sistema necessárias para compilar extensões nativas
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Instala tudo em /build/wheels para copiar na imagem final
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt


# =============================================================================
# Runtime stage — imagem final enxuta
# =============================================================================
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Dependências de sistema em runtime (pillow, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libjpeg62-turbo \
    libpng16-16 \
    libwebp7 \
    && rm -rf /var/lib/apt/lists/*

# Copia pacotes instalados no build stage
COPY --from=builder /install /usr/local

# Copia o código-fonte
COPY src/ ./src/

# Usuário não-root para produção
RUN useradd --no-create-home --shell /bin/false appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info", \
     "--no-access-log"]
