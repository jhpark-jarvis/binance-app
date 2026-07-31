import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MarketCandle(Base):
    __tablename__ = "market_candles"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    interval: Mapped[str] = mapped_column(String(10), primary_key=True)
    open_time: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    close_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    open_price: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    high_price: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    low_price: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    close_price: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    quote_volume: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    trade_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_event_time: Mapped[int | None] = mapped_column(BigInteger)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AggregateTrade(Base):
    __tablename__ = "aggregate_trades"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    aggregate_trade_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    trade_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    first_trade_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_trade_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_buyer_maker: Mapped[bool] = mapped_column(Boolean, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IngestionCheckpoint(Base):
    __tablename__ = "ingestion_checkpoints"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    source: Mapped[str] = mapped_column(String(30), primary_key=True)
    connection_status: Mapped[str] = mapped_column(String(20), nullable=False, default="STARTING")
    last_event_time: Mapped[int | None] = mapped_column(BigInteger)
    last_persisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    reconnect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        UniqueConstraint("symbol", "run_type", "started_at", name="uq_ingestion_run"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    run_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RUNNING")
    range_start: Mapped[int | None] = mapped_column(BigInteger)
    range_end: Mapped[int | None] = mapped_column(BigInteger)
    rows_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
