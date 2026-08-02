import time
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import AggregateTrade, IngestionCheckpoint, IngestionRun, MarketCandle

ONE_MINUTE_MS = 60_000
RECENT_COMPLETED_CANDLE_WINDOW = 60
STALE_EVENT_THRESHOLD_SECONDS = 15
DETAIL_WINDOW_MINUTES = {"1h": 60, "6h": 6 * 60, "24h": 24 * 60, "7d": 7 * 24 * 60}


def _number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def count_missing_completed_minutes(
    closed_open_times: set[int],
    last_completed_open: int,
    window: int = RECENT_COMPLETED_CANDLE_WINDOW,
) -> int:
    expected_start = last_completed_open - (window - 1) * ONE_MINUTE_MS
    return sum(
        minute not in closed_open_times
        for minute in range(expected_start, last_completed_open + ONE_MINUTE_MS, ONE_MINUTE_MS)
    )


def derive_checkpoint_status(
    reported_status: str, last_event_time: int | None, now_ms: int
) -> tuple[str, int | None]:
    """Derive the current operational state from persisted heartbeat age."""
    if last_event_time is None:
        return ("STARTING", None)

    event_age_seconds = max(0, (now_ms - last_event_time) // 1000)
    if reported_status == "LIVE" and event_age_seconds > STALE_EVENT_THRESHOLD_SECONDS:
        return ("STALE", event_age_seconds)
    return (reported_status, event_age_seconds)


def detail_window_minutes(window: str) -> int:
    """Return a supported chart window without accepting arbitrary large queries."""
    try:
        return DETAIL_WINDOW_MINUTES[window]
    except KeyError as error:
        supported = ", ".join(DETAIL_WINDOW_MINUTES)
        raise ValueError(f"Unsupported chart window: {window}. Supported: {supported}") from error


def missing_completed_open_times(
    closed_open_times: set[int], start_open: int, last_completed_open: int
) -> list[int]:
    if start_open > last_completed_open:
        return []
    return [
        open_time
        for open_time in range(start_open, last_completed_open + ONE_MINUTE_MS, ONE_MINUTE_MS)
        if open_time not in closed_open_times
    ]


def reconciliation_observation(
    symbol: str,
    latest_run: IngestionRun | None,
    last_success: IngestionRun | None,
    last_failure: IngestionRun | None,
    failures_since_success: int,
) -> dict[str, object]:
    """Build a compact operational view from persisted reconciliation run history."""
    latest_status = latest_run.status if latest_run else "NOT_RUN"
    return {
        "symbol": symbol,
        "latest_status": latest_status,
        "latest_started_at": latest_run.started_at.isoformat() if latest_run else None,
        "latest_finished_at": latest_run.finished_at.isoformat() if latest_run else None,
        "last_success_at": last_success.finished_at.isoformat() if last_success else None,
        "last_failure_at": last_failure.finished_at.isoformat() if last_failure else None,
        "last_failure_error": last_failure.error_message if last_failure else None,
        "consecutive_failures": failures_since_success if latest_status == "FAILED" else 0,
    }


async def build_dashboard(session: AsyncSession, symbols: tuple[str, ...]) -> dict[str, object]:
    now_ms = int(time.time() * 1000)
    markets = [await _market_summary(session, symbol, now_ms) for symbol in symbols]
    checkpoints = await _checkpoints(session, now_ms)
    runs = await _recent_runs(session)
    reconciliation = await _reconciliation_observations(session, symbols)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "markets": markets,
        "checkpoints": checkpoints,
        "runs": runs,
        "reconciliation": reconciliation,
    }


async def build_market_detail(
    session: AsyncSession, symbol: str, window: str, now_ms: int | None = None
) -> dict[str, object]:
    """Build the PostgreSQL-backed chart payload for one configured symbol."""
    minutes = detail_window_minutes(window)
    current_time = now_ms if now_ms is not None else int(time.time() * 1000)
    current_open = (current_time // ONE_MINUTE_MS) * ONE_MINUTE_MS
    start_open = current_open - (minutes - 1) * ONE_MINUTE_MS
    last_completed_open = current_open - ONE_MINUTE_MS

    candles_statement = (
        select(MarketCandle)
        .where(
            MarketCandle.symbol == symbol,
            MarketCandle.interval == "1m",
            MarketCandle.open_time >= start_open,
            MarketCandle.open_time <= current_open,
        )
        .order_by(MarketCandle.open_time.asc())
    )
    candles = (await session.scalars(candles_statement)).all()
    closed_open_times = {
        candle.open_time
        for candle in candles
        if candle.is_closed and candle.open_time <= last_completed_open
    }
    missing_opens = missing_completed_open_times(
        closed_open_times, start_open, last_completed_open
    )

    trades_statement = (
        select(AggregateTrade)
        .where(AggregateTrade.symbol == symbol)
        .order_by(AggregateTrade.trade_time.desc())
        .limit(12)
    )
    trades = (await session.scalars(trades_statement)).all()
    runs_statement = (
        select(IngestionRun)
        .where(IngestionRun.symbol == symbol)
        .order_by(IngestionRun.started_at.desc())
        .limit(5)
    )
    runs = (await session.scalars(runs_statement)).all()
    latest = candles[-1] if candles else None

    return {
        "symbol": symbol,
        "window": window,
        "range_start": start_open,
        "range_end": current_open,
        "generated_at": datetime.now(UTC).isoformat(),
        "latest_price": _number(latest.close_price) if latest else None,
        "latest_price_time": latest.source_event_time if latest else None,
        "missing_open_times": missing_opens,
        "candles": [
            {
                "time": candle.open_time,
                "open": _number(candle.open_price),
                "high": _number(candle.high_price),
                "low": _number(candle.low_price),
                "close": _number(candle.close_price),
                "volume": _number(candle.volume),
                "closed": candle.is_closed,
            }
            for candle in candles
        ],
        "trades": [
            {
                "id": trade.aggregate_trade_id,
                "time": trade.trade_time,
                "price": _number(trade.price),
                "quantity": _number(trade.quantity),
                "taker_side": "SELL" if trade.is_buyer_maker else "BUY",
            }
            for trade in trades
        ],
        "runs": [
            {
                "type": run.run_type,
                "status": run.status,
                "rows_processed": run.rows_processed,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            }
            for run in runs
        ],
    }


async def _market_summary(session: AsyncSession, symbol: str, now_ms: int) -> dict[str, object]:
    latest_statement = (
        select(MarketCandle)
        .where(MarketCandle.symbol == symbol, MarketCandle.interval == "1m")
        .order_by(MarketCandle.open_time.desc())
        .limit(1)
    )
    latest = await session.scalar(latest_statement)
    if latest is None:
        return {
            "symbol": symbol,
            "price": None,
            "change_24h": None,
            "lag_seconds": None,
            "missing_last_hour": None,
            "candles": [],
            "trades": [],
        }

    reference_time = latest.open_time - 24 * 60 * ONE_MINUTE_MS
    reference_statement = (
        select(MarketCandle.close_price)
        .where(
            MarketCandle.symbol == symbol,
            MarketCandle.interval == "1m",
            MarketCandle.open_time >= reference_time,
        )
        .order_by(MarketCandle.open_time.asc())
        .limit(1)
    )
    reference_price = await session.scalar(reference_statement)
    change_24h = None
    if reference_price and reference_price != 0:
        change_24h = float((latest.close_price - reference_price) / reference_price * 100)

    candles_statement = (
        select(MarketCandle)
        .where(MarketCandle.symbol == symbol, MarketCandle.interval == "1m")
        .order_by(MarketCandle.open_time.desc())
        .limit(60)
    )
    candles = list(reversed((await session.scalars(candles_statement)).all()))
    last_completed_open = (now_ms // ONE_MINUTE_MS - 1) * ONE_MINUTE_MS
    expected_start = last_completed_open - (RECENT_COMPLETED_CANDLE_WINDOW - 1) * ONE_MINUTE_MS
    closed_coverage_statement = select(MarketCandle.open_time).where(
        MarketCandle.symbol == symbol,
        MarketCandle.interval == "1m",
        MarketCandle.is_closed.is_(True),
        MarketCandle.open_time >= expected_start,
        MarketCandle.open_time <= last_completed_open,
    )
    closed_opens = set((await session.scalars(closed_coverage_statement)).all())
    missing_last_hour = count_missing_completed_minutes(closed_opens, last_completed_open)

    trades_statement = (
        select(AggregateTrade)
        .where(AggregateTrade.symbol == symbol)
        .order_by(AggregateTrade.trade_time.desc())
        .limit(10)
    )
    trades = (await session.scalars(trades_statement)).all()
    last_data_time = latest.source_event_time or latest.close_time
    return {
        "symbol": symbol,
        "price": _number(latest.close_price),
        "price_time": latest.open_time,
        "change_24h": change_24h,
        "lag_seconds": max(0, (now_ms - last_data_time) // 1000),
        "missing_last_hour": missing_last_hour,
        "candles": [
            {
                "time": candle.open_time,
                "open": _number(candle.open_price),
                "high": _number(candle.high_price),
                "low": _number(candle.low_price),
                "close": _number(candle.close_price),
                "volume": _number(candle.volume),
                "closed": candle.is_closed,
            }
            for candle in candles
        ],
        "trades": [
            {
                "id": trade.aggregate_trade_id,
                "time": trade.trade_time,
                "price": _number(trade.price),
                "quantity": _number(trade.quantity),
                "taker_side": "SELL" if trade.is_buyer_maker else "BUY",
            }
            for trade in trades
        ],
    }


async def _checkpoints(session: AsyncSession, now_ms: int) -> list[dict[str, object]]:
    statement = select(IngestionCheckpoint).order_by(
        IngestionCheckpoint.symbol, IngestionCheckpoint.source
    )
    checkpoints = (await session.scalars(statement)).all()
    result = []
    for checkpoint in checkpoints:
        status, event_age_seconds = derive_checkpoint_status(
            checkpoint.connection_status, checkpoint.last_event_time, now_ms
        )
        result.append(
            {
                "symbol": checkpoint.symbol,
                "source": checkpoint.source,
                "status": status,
                "reported_status": checkpoint.connection_status,
                "last_event_time": checkpoint.last_event_time,
                "event_age_seconds": event_age_seconds,
                "last_persisted_at": checkpoint.last_persisted_at.isoformat()
                if checkpoint.last_persisted_at
                else None,
                "last_error": checkpoint.last_error,
                "reconnect_count": checkpoint.reconnect_count,
                "updated_at": checkpoint.updated_at.isoformat() if checkpoint.updated_at else None,
            }
        )
    return result


async def _recent_runs(session: AsyncSession) -> list[dict[str, object]]:
    statement = select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(10)
    runs = (await session.scalars(statement)).all()
    return [
        {
            "symbol": run.symbol,
            "type": run.run_type,
            "status": run.status,
            "range_start": run.range_start,
            "range_end": run.range_end,
            "rows_processed": run.rows_processed,
            "error": run.error_message,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        }
        for run in runs
    ]


async def _reconciliation_observations(
    session: AsyncSession, symbols: tuple[str, ...]
) -> list[dict[str, object]]:
    observations = []
    for symbol in symbols:
        base_filters = (
            IngestionRun.symbol == symbol,
            IngestionRun.run_type == "RECONCILIATION",
        )
        latest_run = await session.scalar(
            select(IngestionRun)
            .where(*base_filters)
            .order_by(IngestionRun.started_at.desc())
            .limit(1)
        )
        last_success = await session.scalar(
            select(IngestionRun)
            .where(*base_filters, IngestionRun.status == "SUCCESS")
            .order_by(IngestionRun.started_at.desc())
            .limit(1)
        )
        last_failure = await session.scalar(
            select(IngestionRun)
            .where(*base_filters, IngestionRun.status == "FAILED")
            .order_by(IngestionRun.started_at.desc())
            .limit(1)
        )
        failure_filters = [*base_filters, IngestionRun.status == "FAILED"]
        if last_success is not None:
            failure_filters.append(IngestionRun.started_at > last_success.started_at)
        failures_since_success = await session.scalar(select(func.count()).where(*failure_filters))
        observations.append(
            reconciliation_observation(
                symbol,
                latest_run,
                last_success,
                last_failure,
                failures_since_success or 0,
            )
        )
    return observations
