import asyncio
import logging
import time
from collections.abc import Iterable
from contextlib import suppress

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.core.events import MarketEventPublisher
from app.etl.binance import BinanceMarketClient
from app.etl.repository import MarketRepository
from app.etl.types import Candle, Trade

logger = logging.getLogger(__name__)

ONE_MINUTE_MS = 60_000


def first_missing_open_time(
    closed_open_times: set[int], coverage_start: int, last_completed_open: int
) -> int | None:
    """Return the earliest expected completed candle that is absent from storage."""
    return next(
        (
            open_time
            for open_time in range(
                coverage_start, last_completed_open + ONE_MINUTE_MS, ONE_MINUTE_MS
            )
            if open_time not in closed_open_times
        ),
        None,
    )


class Collector:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker,
        redis: Redis,
    ) -> None:
        if settings.kline_interval != "1m":
            raise ValueError("Initial implementation supports only KLINE_INTERVAL=1m")
        self._settings = settings
        self._session_factory = session_factory
        self._repository = MarketRepository()
        self._client = BinanceMarketClient(settings)
        self._publisher = MarketEventPublisher(redis)
        self._stopped = asyncio.Event()

    async def close(self) -> None:
        self._stopped.set()
        await self._client.close()

    async def run_forever(self) -> None:
        attempt = 0
        while not self._stopped.is_set():
            try:
                await self._run_connected()
                attempt = 0
            except asyncio.CancelledError:
                raise
            except Exception as error:
                attempt += 1
                delay = min(60, 2 ** min(attempt, 6)) + (attempt % 3) * 0.25
                logger.exception("Collector connection failed; retrying in %.2fs", delay)
                await self._mark_all_disconnected(str(error))
                await asyncio.sleep(delay)

    async def _run_connected(self) -> None:
        queue: asyncio.Queue[Candle | Trade] = asyncio.Queue(maxsize=20_000)

        async def read_stream() -> None:
            async for event in self._client.stream(
                self._settings.symbols, self._settings.kline_interval
            ):
                await queue.put(event)

        reader = asyncio.create_task(read_stream(), name="binance-websocket-reader")
        try:
            # The reader starts first, buffering events while REST reconciliation runs.
            await self._recover_all_symbols()
            await self._mark_all_live()
            next_reconciliation_at = (
                time.monotonic() + self._settings.reconciliation_interval_seconds
            )
            while not self._stopped.is_set():
                next_event = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {reader, next_event},
                    timeout=max(0, next_reconciliation_at - time.monotonic()),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    next_event.cancel()
                    with suppress(asyncio.CancelledError):
                        await next_event
                    await self._run_periodic_reconciliation()
                    next_reconciliation_at = (
                        time.monotonic() + self._settings.reconciliation_interval_seconds
                    )
                    continue
                if reader in done:
                    if not next_event.done():
                        next_event.cancel()
                        with suppress(asyncio.CancelledError):
                            await next_event
                    reader.result()
                    raise ConnectionError("Binance WebSocket stream ended")
                event = next_event.result()
                batch = [event]
                await asyncio.sleep(0.05)
                while len(batch) < 500:
                    with suppress(asyncio.QueueEmpty):
                        batch.append(queue.get_nowait())
                        continue
                    break
                await self._persist_live_batch(batch)
                if reader.done():
                    reader.result()
        finally:
            reader.cancel()
            with suppress(asyncio.CancelledError):
                await reader

    async def _recover_all_symbols(
        self,
        *,
        run_type: str = "BACKFILL",
        record_noop: bool = False,
        raise_on_error: bool = True,
    ) -> None:
        for symbol in self._settings.symbols:
            try:
                await self._recover_candles(symbol, run_type=run_type, record_noop=record_noop)
            except Exception:
                if raise_on_error:
                    raise
                logger.exception("Periodic reconciliation failed: symbol=%s", symbol)

    async def _run_periodic_reconciliation(self) -> None:
        logger.info("Periodic completed-candle reconciliation started")
        await self._recover_all_symbols(
            run_type="RECONCILIATION", record_noop=True, raise_on_error=False
        )

    async def _recover_candles(
        self, symbol: str, *, run_type: str = "BACKFILL", record_noop: bool = False
    ) -> bool:
        now_ms = int(time.time() * 1000)
        last_completed_open = (now_ms // ONE_MINUTE_MS - 1) * ONE_MINUTE_MS
        coverage_start = (
            (now_ms - self._settings.bootstrap_days * 86_400_000) // ONE_MINUTE_MS
        ) * ONE_MINUTE_MS

        async with self._session_factory() as session:
            existing = await self._repository.closed_open_times(
                session, symbol, self._settings.kline_interval, coverage_start, last_completed_open
            )

        missing_start = first_missing_open_time(existing, coverage_start, last_completed_open)
        if missing_start is None:
            if record_noop:
                await self._record_successful_reconciliation(
                    symbol, coverage_start, last_completed_open
                )
            return False

        reconciliation_start = max(
            coverage_start,
            missing_start - self._settings.backfill_overlap_minutes * ONE_MINUTE_MS,
        )

        rows_processed = 0
        logger.info(
            "Backfill started: symbol=%s start=%s end=%s",
            symbol,
            reconciliation_start,
            last_completed_open,
        )
        async with self._session_factory() as session:
            run = await self._repository.create_run(
                session, symbol, run_type, reconciliation_start, last_completed_open
            )
            await session.commit()

        try:
            next_start = reconciliation_start
            while next_start <= last_completed_open:
                candles = await self._client.fetch_klines(
                    symbol, self._settings.kline_interval, next_start, last_completed_open
                )
                if not candles:
                    break
                async with self._session_factory() as session:
                    await self._repository.upsert_candles(session, candles)
                    await session.commit()
                rows_processed += len(candles)
                next_start = candles[-1].open_time + ONE_MINUTE_MS

            async with self._session_factory() as session:
                persisted = await self._repository.closed_open_times(
                    session,
                    symbol,
                    self._settings.kline_interval,
                    coverage_start,
                    last_completed_open,
                )
            remaining_missing = first_missing_open_time(
                persisted, coverage_start, last_completed_open
            )
            if remaining_missing is not None:
                raise RuntimeError(
                    "Completed-candle reconciliation is incomplete: "
                    f"symbol={symbol} missing_open_time={remaining_missing}"
                )

            async with self._session_factory() as session:
                await self._repository.finish_run(
                    session, run, status="SUCCESS", rows_processed=rows_processed
                )
                await self._repository.update_checkpoint(
                    session,
                    symbol,
                    "KLINE_1M",
                    status="RECOVERED",
                    last_event_time=last_completed_open,
                )
                await session.commit()
            await self._publisher.publish(
                "backfill_completed",
                {
                    "symbol": symbol,
                    "type": run_type,
                    "start": reconciliation_start,
                    "end": last_completed_open,
                    "rows": rows_processed,
                },
            )
            return True
        except Exception as error:
            async with self._session_factory() as session:
                await self._repository.finish_run(
                    session, run, status="FAILED", rows_processed=rows_processed, error=str(error)
                )
                await self._repository.update_checkpoint(
                    session, symbol, "KLINE_1M", status="FAILED", error=str(error)
                )
                await session.commit()
            raise

    async def _record_successful_reconciliation(
        self, symbol: str, range_start: int, range_end: int
    ) -> None:
        async with self._session_factory() as session:
            run = await self._repository.create_run(
                session, symbol, "RECONCILIATION", range_start, range_end
            )
            await self._repository.finish_run(
                session, run, status="SUCCESS", rows_processed=0
            )
            await session.commit()

    async def _persist_live_batch(self, events: Iterable[Candle | Trade]) -> None:
        candles = [event for event in events if isinstance(event, Candle)]
        trades = [event for event in events if isinstance(event, Trade)]
        async with self._session_factory() as session:
            await self._repository.upsert_candles(session, candles)
            await self._repository.insert_trades(session, trades)
            for candle in candles:
                await self._repository.update_checkpoint(
                    session,
                    candle.symbol,
                    "KLINE_1M",
                    status="LIVE",
                    last_event_time=candle.source_event_time,
                )
            for trade in trades:
                await self._repository.update_checkpoint(
                    session,
                    trade.symbol,
                    "AGG_TRADE",
                    status="LIVE",
                    last_event_time=trade.event_time,
                )
            await session.commit()

        for candle in candles:
            snapshot = {
                "symbol": candle.symbol,
                "price": str(candle.close_price),
                "event_time": candle.source_event_time,
                "is_closed": candle.is_closed,
            }
            await self._publisher.cache_snapshot(candle.symbol, snapshot)
            await self._publisher.publish("candle", snapshot)
        for trade in trades:
            await self._publisher.publish(
                "trade",
                {
                    "symbol": trade.symbol,
                    "id": trade.aggregate_trade_id,
                    "price": str(trade.price),
                    "quantity": str(trade.quantity),
                    "trade_time": trade.trade_time,
                    "taker_side": "SELL" if trade.is_buyer_maker else "BUY",
                },
            )

    async def _mark_all_live(self) -> None:
        async with self._session_factory() as session:
            for symbol in self._settings.symbols:
                for source in ("KLINE_1M", "AGG_TRADE"):
                    await self._repository.update_checkpoint(session, symbol, source, status="LIVE")
            await session.commit()

    async def _mark_all_disconnected(self, error: str) -> None:
        async with self._session_factory() as session:
            for symbol in self._settings.symbols:
                for source in ("KLINE_1M", "AGG_TRADE"):
                    await self._repository.update_checkpoint(
                        session,
                        symbol,
                        source,
                        status="RECONNECTING",
                        error=error[:1000],
                        increment_reconnect=True,
                    )
            await session.commit()
