import asyncio
import json
from collections.abc import AsyncIterator
from decimal import Decimal
from urllib.parse import urlencode

import httpx
from websockets.asyncio.client import connect

from app.core.config import Settings
from app.etl.types import Candle, Trade


class BinanceMarketClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._http = httpx.AsyncClient(
            base_url=str(settings.binance_rest_url).rstrip("/"), timeout=15.0
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def fetch_klines(
        self, symbol: str, interval: str, start_time: int, end_time: int, limit: int = 1000
    ) -> list[Candle]:
        response = await self._get(
            "/api/v3/klines",
            {
                "symbol": symbol,
                "interval": interval,
                "startTime": start_time,
                "endTime": end_time,
                "limit": limit,
            },
        )
        response.raise_for_status()
        return [self._candle_from_rest(symbol, interval, item) for item in response.json()]

    async def fetch_aggregate_trades(
        self, symbol: str, start_time: int, end_time: int, limit: int = 1000
    ) -> list[Trade]:
        response = await self._get(
            "/api/v3/aggTrades",
            {
                "symbol": symbol,
                "startTime": start_time,
                "endTime": end_time,
                "limit": limit,
            },
        )
        response.raise_for_status()
        return [self._trade_from_payload(item, symbol) for item in response.json()]

    async def stream(
        self, symbols: tuple[str, ...], interval: str
    ) -> AsyncIterator[Candle | Trade]:
        streams = []
        for symbol in symbols:
            normalized = symbol.lower()
            streams.extend((f"{normalized}@aggTrade", f"{normalized}@kline_{interval}"))
        url = f"{self._settings.binance_ws_url}?{urlencode({'streams': '/'.join(streams)})}"
        async with connect(url, ping_interval=20, ping_timeout=20) as websocket:
            async for raw_message in websocket:
                payload = json.loads(raw_message)
                data = payload["data"]
                event_type = data.get("e")
                if event_type == "aggTrade":
                    yield self._trade_from_payload(data, data["s"])
                elif event_type == "kline":
                    yield self._candle_from_stream(data)

    async def _get(self, path: str, params: dict[str, object]) -> httpx.Response:
        """Respect exchange throttling and retry transient REST failures."""
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                response = await self._http.get(path, params=params)
                if response.status_code not in {418, 429} and response.status_code < 500:
                    response.raise_for_status()
                    return response
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(30, 2**attempt)
                last_error = httpx.HTTPStatusError(
                    f"Binance returned {response.status_code}",
                    request=response.request,
                    response=response,
                )
            except httpx.HTTPError as error:
                last_error = error
                delay = min(30, 2**attempt)
            await asyncio.sleep(delay + 0.1 * attempt)
        assert last_error is not None
        raise last_error

    @staticmethod
    def _candle_from_rest(symbol: str, interval: str, item: list[object]) -> Candle:
        return Candle(
            symbol=symbol,
            interval=interval,
            open_time=int(item[0]),
            open_price=Decimal(str(item[1])),
            high_price=Decimal(str(item[2])),
            low_price=Decimal(str(item[3])),
            close_price=Decimal(str(item[4])),
            volume=Decimal(str(item[5])),
            close_time=int(item[6]),
            quote_volume=Decimal(str(item[7])),
            trade_count=int(item[8]),
            is_closed=True,
            source_event_time=None,
        )

    @staticmethod
    def _candle_from_stream(data: dict[str, object]) -> Candle:
        kline = data["k"]
        assert isinstance(kline, dict)
        return Candle(
            symbol=str(data["s"]),
            interval=str(kline["i"]),
            open_time=int(kline["t"]),
            close_time=int(kline["T"]),
            open_price=Decimal(str(kline["o"])),
            high_price=Decimal(str(kline["h"])),
            low_price=Decimal(str(kline["l"])),
            close_price=Decimal(str(kline["c"])),
            volume=Decimal(str(kline["v"])),
            quote_volume=Decimal(str(kline["q"])),
            trade_count=int(kline["n"]),
            is_closed=bool(kline["x"]),
            source_event_time=int(data["E"]),
        )

    @staticmethod
    def _trade_from_payload(data: dict[str, object], symbol: str) -> Trade:
        return Trade(
            symbol=symbol,
            aggregate_trade_id=int(data["a"]),
            price=Decimal(str(data["p"])),
            quantity=Decimal(str(data["q"])),
            first_trade_id=int(data["f"]),
            last_trade_id=int(data["l"]),
            trade_time=int(data["T"]),
            event_time=int(data.get("E", data["T"])),
            is_buyer_maker=bool(data["m"]),
        )
