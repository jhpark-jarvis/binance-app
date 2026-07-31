import time
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import AggregateTrade, IngestionCheckpoint, IngestionRun, MarketCandle

ONE_MINUTE_MS = 60_000


def _number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


async def build_dashboard(session: AsyncSession, symbols: tuple[str, ...]) -> dict[str, object]:
    now_ms = int(time.time() * 1000)
    markets = [await _market_summary(session, symbol, now_ms) for symbol in symbols]
    checkpoints = await _checkpoints(session)
    runs = await _recent_runs(session)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "markets": markets,
        "checkpoints": checkpoints,
        "runs": runs,
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
    closed_opens = {candle.open_time for candle in candles if candle.is_closed}
    last_completed_open = (now_ms // ONE_MINUTE_MS - 1) * ONE_MINUTE_MS
    expected_start = last_completed_open - 59 * ONE_MINUTE_MS
    missing_last_hour = sum(
        minute not in closed_opens
        for minute in range(expected_start, last_completed_open + ONE_MINUTE_MS, ONE_MINUTE_MS)
    )

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


async def _checkpoints(session: AsyncSession) -> list[dict[str, object]]:
    statement = select(IngestionCheckpoint).order_by(
        IngestionCheckpoint.symbol, IngestionCheckpoint.source
    )
    checkpoints = (await session.scalars(statement)).all()
    return [
        {
            "symbol": checkpoint.symbol,
            "source": checkpoint.source,
            "status": checkpoint.connection_status,
            "last_event_time": checkpoint.last_event_time,
            "last_persisted_at": checkpoint.last_persisted_at.isoformat()
            if checkpoint.last_persisted_at
            else None,
            "last_error": checkpoint.last_error,
            "reconnect_count": checkpoint.reconnect_count,
            "updated_at": checkpoint.updated_at.isoformat() if checkpoint.updated_at else None,
        }
        for checkpoint in checkpoints
    ]


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
