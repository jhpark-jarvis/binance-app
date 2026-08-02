"""Docker healthcheck for the long-running ETL collector."""

import asyncio
import sys
import time
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal, dispose_engine
from app.core.models import IngestionCheckpoint

EXPECTED_SOURCES = ("KLINE_1M", "AGG_TRADE")
HEALTHY_STATUSES = {"LIVE", "RECOVERED"}


def checkpoint_health_issues(
    checkpoints: Iterable[IngestionCheckpoint],
    symbols: tuple[str, ...],
    max_event_age_seconds: int,
    now_ms: int,
) -> list[str]:
    """Return every missing, stale, or non-live expected collector checkpoint."""
    observed = {(checkpoint.symbol, checkpoint.source): checkpoint for checkpoint in checkpoints}
    issues: list[str] = []
    for symbol in symbols:
        for source in EXPECTED_SOURCES:
            checkpoint = observed.get((symbol, source))
            label = f"{symbol}/{source}"
            if checkpoint is None:
                issues.append(f"{label}: checkpoint missing")
                continue
            if checkpoint.connection_status not in HEALTHY_STATUSES:
                issues.append(f"{label}: status={checkpoint.connection_status}")
                continue
            if checkpoint.last_event_time is None:
                issues.append(f"{label}: event missing")
                continue
            age_seconds = max(0, (now_ms - checkpoint.last_event_time) // 1000)
            if age_seconds > max_event_age_seconds:
                issues.append(f"{label}: event age={age_seconds}s")
    return issues


async def etl_health_issues(
    session: AsyncSession,
    symbols: tuple[str, ...],
    max_event_age_seconds: int,
    now_ms: int | None = None,
) -> list[str]:
    checkpoints = (await session.scalars(select(IngestionCheckpoint))).all()
    return checkpoint_health_issues(
        checkpoints,
        symbols,
        max_event_age_seconds,
        int(time.time() * 1000) if now_ms is None else now_ms,
    )


async def run_healthcheck() -> int:
    settings = get_settings()
    try:
        async with SessionLocal() as session:
            issues = await etl_health_issues(
                session,
                settings.symbols,
                settings.etl_health_max_event_age_seconds,
            )
    except Exception as error:
        print(f"ETL unhealthy: database check failed: {error}")
        return 1
    finally:
        await dispose_engine()

    if issues:
        print(f"ETL unhealthy: {'; '.join(issues)}")
        return 1
    print("ETL healthy")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_healthcheck()))
