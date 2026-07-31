from app.core.config import Settings


def test_symbols_are_normalized() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        redis_url="redis://localhost:6379/0",
        SYMBOLS="btcusdt, ethusdt",
    )

    assert settings.symbols == ("BTCUSDT", "ETHUSDT")
