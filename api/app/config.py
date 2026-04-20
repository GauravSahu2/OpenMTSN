"""Environment-driven configuration using Pydantic Settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # ── Redis ─────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_NODE_TTL_SECONDS: int = 30

    # ── CORS ──────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ── Application ───────────────────────────────────
    LOG_LEVEL: str = "INFO"
    APP_TITLE: str = "OpenMTSN Control Plane"
    APP_VERSION: str = "0.1.0"

    # ── Routing thresholds ────────────────────────────
    PACKET_LOSS_FAILOVER_THRESHOLD: float = 15.0
    SIGNAL_STRENGTH_FAILOVER_THRESHOLD: int = 30
    LATENCY_WARNING_THRESHOLD_MS: float = 200.0

    # ── Security ──────────────────────────────────────
    API_KEY: str = "openmtsn-secret-key-2026"
    DASHBOARD_SECRET: str = "dashboard-access-key-2026"
    SECURITY_ENABLED: bool = True

    # ── PKI (mTLS) ────────────────────────────────────
    # Paths relative to the API root
    CA_CERT_PATH: str = "/certs/ca.crt"
    SERVER_CERT_PATH: str = "/certs/server.crt"
    SERVER_KEY_PATH: str = "/certs/server.key"
    MTLS_REQUIRED: bool = True

    model_config = {"env_prefix": "MTSN_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
