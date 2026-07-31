from functools import lru_cache

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    redis_url: str
    symbols_raw: str = Field(default="BTCUSDT,ETHUSDT", validation_alias="SYMBOLS")
    kline_interval: str = "1m"
    bootstrap_days: int = Field(default=7, ge=1, le=90)
    backfill_overlap_minutes: int = Field(default=2, ge=0, le=10)
    binance_rest_url: HttpUrl = "https://api.binance.com"
    binance_ws_url: str = "wss://stream.binance.com:9443/stream"
    web_host: str = "0.0.0.0"
    web_port: int = 8000

    @property
    def symbols(self) -> tuple[str, ...]:
        values = tuple(
            symbol.strip().upper() for symbol in self.symbols_raw.split(",") if symbol.strip()
        )
        if not values:
            raise ValueError("At least one market symbol must be configured")
        return values


@lru_cache
def get_settings() -> Settings:
    return Settings()
