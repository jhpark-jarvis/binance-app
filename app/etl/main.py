import asyncio
import logging
import signal

from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.database import SessionLocal, dispose_engine
from app.etl.collector import Collector


async def run() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    collector = Collector(settings, SessionLocal, redis)
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    def request_stop() -> None:
        stop.set()

    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, request_stop)
        except NotImplementedError:
            signal.signal(signal_name, lambda *_: request_stop())

    task = asyncio.create_task(collector.run_forever())
    await stop.wait()
    await collector.close()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await redis.aclose()
    await dispose_engine()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    asyncio.run(run())
