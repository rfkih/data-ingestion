"""Centralised settings via pydantic-settings.

All env vars prefixed `INGEST_` to avoid collisions with the trading JVM's
own env (`SPRING_*`, `JWT_*`, etc.) when both run on the same host.
"""
from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INGEST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Postgres — shared with trading JVM.
    # Set either db_dsn (full DSN string) OR the individual fields below.
    # db_dsn takes precedence when set.
    db_dsn: str = ""
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "trading_db"
    db_user: str = "blackheart_trading"
    db_password: str = ""

    server_host: str = "127.0.0.1"
    server_port: int = 8089

    fred_api_key: str = ""

    # Inference webhook settings for batch-predict trigger after feature compute.
    inference_base_url: str = "http://127.0.0.1:8000"
    inference_auth_token: SecretStr = SecretStr("")

    default_max_backfill_lag_hours: int = Field(default=72, ge=1, le=8760)
    log_level: str = "INFO"

    # Automatic feature compute loop (background task inside the ingest server).
    # Set INGEST_COMPUTE_AUTO=true to enable; disabled by default so existing
    # deployments are not silently changed.
    compute_auto: bool = False
    compute_interval_hours: int = Field(default=4, ge=1, le=168)
    compute_lookback_hours: int = Field(default=72, ge=1, le=8760)

    # Kafka bar-event consumer.
    # When enabled, subscribes to market.bars and triggers per-bar feature compute
    # on each closed bar — replacing the Windows Task Scheduler cron.
    # Requires aiokafka: pip install blackheart-ingest[kafka]
    kafka_enabled: bool = False
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "blackheart-ingest"

    # Binance USDT-M futures liquidation stream (forceOrder accrual worker).
    # Liquidations are NOT backfillable -- the worker accrues them live into
    # macro_raw (source=binance_liquidation, all symbols). Default OFF so
    # deploying the code is inert; set INGEST_LIQUIDATION_STREAM_ENABLED=true
    # to start accruing (same pattern as the inference streaming worker).
    liquidation_stream_enabled: bool = False
    liquidation_ws_url: str = "wss://fstream.binance.com/market/ws/!forceOrder@arr"
    liquidation_flush_max_rows: int = Field(default=200, ge=1, le=10_000)
    liquidation_flush_seconds: float = Field(default=5.0, ge=0.5, le=300)

    def db_kwargs(self) -> dict[str, object]:
        """Connection keyword args for ``psycopg.connect(**kwargs)``.

        If INGEST_DB_DSN is set it is parsed and takes precedence over the
        individual INGEST_DB_* fields, so a single env var is enough in
        Docker/CI deployments.
        """
        if self.db_dsn:
            p = urlparse(self.db_dsn)
            return {
                "host": p.hostname or self.db_host,
                "port": p.port or self.db_port,
                "dbname": (p.path or "").lstrip("/") or self.db_name,
                "user": p.username or self.db_user,
                "password": p.password or self.db_password,
            }
        return {
            "host": self.db_host,
            "port": self.db_port,
            "dbname": self.db_name,
            "user": self.db_user,
            "password": self.db_password,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
