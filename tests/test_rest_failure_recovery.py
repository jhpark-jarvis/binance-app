import httpx
import pytest

from app.core.config import Settings
from app.etl.binance import BinanceMarketClient
from app.etl.collector import Collector


class FakeSession:
    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def commit(self) -> None:
        return None


class FakeSessionFactory:
    def __call__(self) -> FakeSession:
        return FakeSession()


class RecordingRepository:
    def __init__(self) -> None:
        self.finished_runs: list[dict[str, object]] = []
        self.checkpoint_updates: list[dict[str, object]] = []

    async def closed_open_times(self, *_: object) -> set[int]:
        return set()

    async def create_run(self, *_: object) -> object:
        return object()

    async def finish_run(self, _: FakeSession, __: object, **kwargs: object) -> None:
        self.finished_runs.append(kwargs)

    async def update_checkpoint(self, _: FakeSession, *args: object, **kwargs: object) -> None:
        self.checkpoint_updates.append({"args": args, **kwargs})


class FailingKlineClient:
    async def fetch_klines(self, *_: object) -> list[object]:
        raise httpx.ConnectError("REST endpoint unavailable")

    async def close(self) -> None:
        return None


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        redis_url="redis://localhost:6379/0",
        SYMBOLS="BTCUSDT",
        bootstrap_days=1,
    )


@pytest.mark.asyncio
async def test_rest_client_retries_transient_server_failure_five_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def unavailable(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, request=request)

    async def no_wait(_: float) -> None:
        return None

    client = BinanceMarketClient(_settings())
    await client.close()
    client._http = httpx.AsyncClient(
        base_url="https://binance.test", transport=httpx.MockTransport(unavailable)
    )
    monkeypatch.setattr("app.etl.binance.asyncio.sleep", no_wait)

    with pytest.raises(httpx.HTTPStatusError):
        await client.fetch_klines("BTCUSDT", "1m", 1_710_000_000_000, 1_710_000_060_000)

    await client.close()
    assert attempts == 5


@pytest.mark.asyncio
async def test_backfill_rest_failure_records_failed_run_and_checkpoint() -> None:
    collector = Collector(_settings(), FakeSessionFactory(), None)
    await collector._client.close()
    repository = RecordingRepository()
    collector._repository = repository
    collector._client = FailingKlineClient()

    with pytest.raises(httpx.ConnectError, match="REST endpoint unavailable"):
        await collector._recover_candles("BTCUSDT", run_type="RECONCILIATION")

    assert repository.finished_runs == [
        {
            "status": "FAILED",
            "rows_processed": 0,
            "error": "REST endpoint unavailable",
        }
    ]
    assert repository.checkpoint_updates == [
        {
            "args": ("BTCUSDT", "KLINE_1M"),
            "status": "FAILED",
            "error": "REST endpoint unavailable",
        }
    ]

    await collector.close()
