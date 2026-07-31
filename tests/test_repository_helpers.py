from decimal import Decimal

from app.etl.repository import deduplicate_candles
from app.etl.types import Candle
from app.web.dashboard import ONE_MINUTE_MS, count_missing_completed_minutes


def _candle(close_price: str, event_time: int) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        interval="1m",
        open_time=1_710_000_000_000,
        close_time=1_710_000_059_999,
        open_price=Decimal("62000"),
        high_price=Decimal("62010"),
        low_price=Decimal("61990"),
        close_price=Decimal(close_price),
        volume=Decimal("1"),
        quote_volume=Decimal("62000"),
        trade_count=10,
        is_closed=False,
        source_event_time=event_time,
    )


def test_candle_batch_uses_last_update_for_duplicate_identity() -> None:
    first = _candle("62001", 1_710_000_001_000)
    latest = _candle("62002", 1_710_000_002_000)

    deduplicated = deduplicate_candles((first, latest))

    assert len(deduplicated) == 1
    assert deduplicated[0].close_price == Decimal("62002")


def test_missing_candle_count_uses_only_completed_candle_window() -> None:
    last_completed = 1_710_000_000_000
    closed_open_times = {last_completed - offset * ONE_MINUTE_MS for offset in range(60)}

    assert count_missing_completed_minutes(closed_open_times, last_completed) == 0
