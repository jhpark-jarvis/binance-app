from decimal import Decimal

from app.core.models import IngestionCheckpoint
from app.etl.collector import ONE_MINUTE_MS as COLLECTOR_ONE_MINUTE_MS
from app.etl.collector import first_missing_open_time
from app.etl.health import checkpoint_health_issues
from app.etl.repository import deduplicate_candles
from app.etl.types import Candle
from app.web.dashboard import (
    ONE_MINUTE_MS,
    STALE_EVENT_THRESHOLD_SECONDS,
    count_missing_completed_minutes,
    derive_checkpoint_status,
    detail_window_minutes,
    missing_completed_open_times,
)


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


def test_live_checkpoint_becomes_stale_when_heartbeat_is_old() -> None:
    now_ms = 1_710_000_000_000
    status, age_seconds = derive_checkpoint_status(
        "LIVE", now_ms - (STALE_EVENT_THRESHOLD_SECONDS + 1) * 1000, now_ms
    )

    assert status == "STALE"
    assert age_seconds == STALE_EVENT_THRESHOLD_SECONDS + 1


def test_detail_window_is_limited_to_supported_operational_ranges() -> None:
    assert detail_window_minutes("6h") == 360


def test_detail_missing_times_excludes_current_open_candle() -> None:
    last_completed = 1_710_000_000_000
    closed = {last_completed - offset * ONE_MINUTE_MS for offset in (0, 2)}

    missing = missing_completed_open_times(
        closed, last_completed - 2 * ONE_MINUTE_MS, last_completed
    )

    assert missing == [last_completed - ONE_MINUTE_MS]


def test_first_missing_open_time_returns_the_earliest_gap() -> None:
    coverage_start = 1_710_000_000_000
    existing = {
        coverage_start,
        coverage_start + 2 * COLLECTOR_ONE_MINUTE_MS,
    }

    assert (
        first_missing_open_time(
            existing, coverage_start, coverage_start + 2 * COLLECTOR_ONE_MINUTE_MS
        )
        == coverage_start + COLLECTOR_ONE_MINUTE_MS
    )


def test_etl_health_requires_all_recent_live_checkpoints() -> None:
    now_ms = 1_710_000_000_000
    checkpoints = [
        IngestionCheckpoint(
            symbol="BTCUSDT",
            source=source,
            connection_status="LIVE",
            last_event_time=now_ms - 5_000,
        )
        for source in ("KLINE_1M", "AGG_TRADE")
    ]

    assert checkpoint_health_issues(checkpoints, ("BTCUSDT",), 60, now_ms) == []

    checkpoints[1].connection_status = "RECONNECTING"
    assert checkpoint_health_issues(checkpoints, ("BTCUSDT",), 60, now_ms) == [
        "BTCUSDT/AGG_TRADE: status=RECONNECTING"
    ]


def test_etl_health_rejects_a_stale_checkpoint() -> None:
    now_ms = 1_710_000_000_000
    checkpoints = [
        IngestionCheckpoint(
            symbol="BTCUSDT",
            source=source,
            connection_status="LIVE",
            last_event_time=now_ms - 61_000,
        )
        for source in ("KLINE_1M", "AGG_TRADE")
    ]

    assert checkpoint_health_issues(checkpoints, ("BTCUSDT",), 60, now_ms) == [
        "BTCUSDT/KLINE_1M: event age=61s",
        "BTCUSDT/AGG_TRADE: event age=61s",
    ]
