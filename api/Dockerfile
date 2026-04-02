# ── Stage 1: Build ────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .

# ── Stage 2: Runtime ─────────────────────────────────────
FROM python:3.12-slim

LABEL org.opencontainers.image.title="OpenMTSN Control Plane"
LABEL org.opencontainers.image.source="https://github.com/openmtsn/openmtsn"

RUN groupadd -r mtsn && useradd -r -g mtsn mtsn
WORKDIR /app

COPY --from=builder /install /usr/local
COPY app/ ./app/

USER mtsn
EXPOSE 8000

ENV MTSN_REDIS_URL="redis://redis:6379/0"
ENV MTSN_LOG_LEVEL="INFO"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
