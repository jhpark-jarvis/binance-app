from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import AggregateTrade, IngestionCheckpoint, IngestionRun, MarketCandle
from app.etl.types import Candle, Trade


def deduplicate_candles(candles: Iterable[Candle]) -> list[Candle]:
    """Keep the final update for each candle identity within an insert batch."""
    deduplicated = {
        (candle.symbol, candle.interval, candle.open_time): candle for candle in candles
    }
    return list(deduplicated.values())


class MarketRepository:
    async def latest_closed_candle(
        self, session: AsyncSession, symbol: str, interval: str
    ) -> int | None:
        statement = select(func.max(MarketCandle.open_time)).where(
            MarketCandle.symbol == symbol,
            MarketCandle.interval == interval,
            MarketCandle.is_closed.is_(True),
        )
        return await session.scalar(statement)

    async def closed_open_times(
        self, session: AsyncSession, symbol: str, interval: str, start: int, end: int
    ) -> set[int]:
        statement = select(MarketCandle.open_time).where(
            MarketCandle.symbol == symbol,
            MarketCandle.interval == interval,
            MarketCandle.is_closed.is_(True),
            MarketCandle.open_time >= start,
            MarketCandle.open_time <= end,
        )
        return set((await session.scalars(statement)).all())

    async def upsert_candles(self, session: AsyncSession, candles: Iterable[Candle]) -> None:
        # A WebSocket batch can include several updates for the same open candle.
        # PostgreSQL rejects duplicate conflict targets within one INSERT statement,
        # so retain only the final (newest) update for each candle identity.
        deduplicated = deduplicate_candles(candles)
        rows = [
            {
                "symbol": candle.symbol,
                "interval": candle.interval,
                "open_time": candle.open_time,
                "close_time": candle.close_time,
                "open_price": candle.open_price,
                "high_price": candle.high_price,
                "low_price": candle.low_price,
                "close_price": candle.close_price,
                "volume": candle.volume,
                "quote_volume": candle.quote_volume,
                "trade_count": candle.trade_count,
                "is_closed": candle.is_closed,
                "source_event_time": candle.source_event_time,
            }
            for candle in deduplicated
        ]
        if not rows:
            return
        statement = insert(MarketCandle).values(rows)
        excluded = statement.excluded
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=["symbol", "interval", "open_time"],
                set_={
                    "close_time": excluded.close_time,
                    "open_price": excluded.open_price,
                    "high_price": excluded.high_price,
                    "low_price": excluded.low_price,
                    "close_price": excluded.close_price,
                    "volume": excluded.volume,
                    "quote_volume": excluded.quote_volume,
                    "trade_count": excluded.trade_count,
                    "is_closed": MarketCandle.is_closed | excluded.is_closed,
                    "source_event_time": excluded.source_event_time,
                    "updated_at": func.now(),
                },
            )
        )

    async def insert_trades(self, session: AsyncSession, trades: Iterable[Trade]) -> None:
        rows = [
            {
                "symbol": trade.symbol,
                "aggregate_trade_id": trade.aggregate_trade_id,
                "event_time": trade.event_time,
                "trade_time": trade.trade_time,
                "price": trade.price,
                "quantity": trade.quantity,
                "first_trade_id": trade.first_trade_id,
                "last_trade_id": trade.last_trade_id,
                "is_buyer_maker": trade.is_buyer_maker,
            }
            for trade in trades
        ]
        if not rows:
            return
        statement = insert(AggregateTrade).values(rows)
        await session.execute(
            statement.on_conflict_do_nothing(index_elements=["symbol", "aggregate_trade_id"])
        )

    async def update_checkpoint(
        self,
        session: AsyncSession,
        symbol: str,
        source: str,
        *,
        status: str,
        last_event_time: int | None = None,
        error: str | None = None,
        increment_reconnect: bool = False,
    ) -> None:
        statement = insert(IngestionCheckpoint).values(
            symbol=symbol,
            source=source,
            connection_status=status,
            last_event_time=last_event_time,
            last_persisted_at=datetime.now(UTC),
            last_error=error,
            reconnect_count=1 if increment_reconnect else 0,
        )
        excluded = statement.excluded
        reconnect_count = (
            IngestionCheckpoint.reconnect_count + 1
            if increment_reconnect
            else IngestionCheckpoint.reconnect_count
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=["symbol", "source"],
                set_={
                    "connection_status": excluded.connection_status,
                    "last_event_time": func.coalesce(
                        excluded.last_event_time, IngestionCheckpoint.last_event_time
                    ),
                    "last_persisted_at": excluded.last_persisted_at,
                    "last_error": excluded.last_error,
                    "reconnect_count": reconnect_count,
                    "updated_at": func.now(),
                },
            )
        )

    async def create_run(
        self, session: AsyncSession, symbol: str, run_type: str, range_start: int, range_end: int
    ) -> IngestionRun:
        run = IngestionRun(
            symbol=symbol,
            run_type=run_type,
            range_start=range_start,
            range_end=range_end,
        )
        session.add(run)
        await session.flush()
        return run

    async def finish_run(
        self,
        session: AsyncSession,
        run: IngestionRun,
        *,
        status: str,
        rows_processed: int,
        error: str | None = None,
    ) -> None:
        managed_run = await session.merge(run)
        managed_run.status = status
        managed_run.rows_processed = rows_processed
        managed_run.error_message = error
        managed_run.finished_at = datetime.now(UTC)
