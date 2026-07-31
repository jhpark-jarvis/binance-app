import json
from collections.abc import Mapping

from redis.asyncio import Redis

MARKET_EVENTS_CHANNEL = "market-events"


class MarketEventPublisher:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def publish(self, event_type: str, payload: Mapping[str, object]) -> None:
        message = json.dumps({"type": event_type, "payload": payload}, default=str)
        await self._redis.publish(MARKET_EVENTS_CHANNEL, message)

    async def cache_snapshot(self, symbol: str, snapshot: Mapping[str, object]) -> None:
        key = f"market:snapshot:{symbol}"
        await self._redis.set(key, json.dumps(snapshot, default=str), ex=30)
