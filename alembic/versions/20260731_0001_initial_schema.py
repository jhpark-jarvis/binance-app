"""initial market data schema

Revision ID: 20260731_0001
Revises:
Create Date: 2026-07-31
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260731_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_candles",
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("interval", sa.String(length=10), nullable=False),
        sa.Column("open_time", sa.BigInteger(), nullable=False),
        sa.Column("close_time", sa.BigInteger(), nullable=False),
        sa.Column("open_price", sa.Numeric(precision=30, scale=12), nullable=False),
        sa.Column("high_price", sa.Numeric(precision=30, scale=12), nullable=False),
        sa.Column("low_price", sa.Numeric(precision=30, scale=12), nullable=False),
        sa.Column("close_price", sa.Numeric(precision=30, scale=12), nullable=False),
        sa.Column("volume", sa.Numeric(precision=30, scale=12), nullable=False),
        sa.Column("quote_volume", sa.Numeric(precision=30, scale=12), nullable=False),
        sa.Column("trade_count", sa.Integer(), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source_event_time", sa.BigInteger(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("symbol", "interval", "open_time"),
    )
    op.create_index("ix_market_candles_symbol_open_time", "market_candles", ["symbol", "open_time"])

    op.create_table(
        "aggregate_trades",
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("aggregate_trade_id", sa.BigInteger(), nullable=False),
        sa.Column("event_time", sa.BigInteger(), nullable=False),
        sa.Column("trade_time", sa.BigInteger(), nullable=False),
        sa.Column("price", sa.Numeric(precision=30, scale=12), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=30, scale=12), nullable=False),
        sa.Column("first_trade_id", sa.BigInteger(), nullable=False),
        sa.Column("last_trade_id", sa.BigInteger(), nullable=False),
        sa.Column("is_buyer_maker", sa.Boolean(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("symbol", "aggregate_trade_id"),
    )
    op.create_index(
        "ix_aggregate_trades_symbol_trade_time", "aggregate_trades", ["symbol", "trade_time"]
    )

    op.create_table(
        "ingestion_checkpoints",
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column(
            "connection_status", sa.String(length=20), nullable=False, server_default="STARTING"
        ),
        sa.Column("last_event_time", sa.BigInteger(), nullable=True),
        sa.Column("last_persisted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("reconnect_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("symbol", "source"),
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("run_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="RUNNING"),
        sa.Column("range_start", sa.BigInteger(), nullable=True),
        sa.Column("range_end", sa.BigInteger(), nullable=True),
        sa.Column("rows_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "run_type", "started_at", name="uq_ingestion_run"),
    )


def downgrade() -> None:
    op.drop_table("ingestion_runs")
    op.drop_table("ingestion_checkpoints")
    op.drop_index("ix_aggregate_trades_symbol_trade_time", table_name="aggregate_trades")
    op.drop_table("aggregate_trades")
    op.drop_index("ix_market_candles_symbol_open_time", table_name="market_candles")
    op.drop_table("market_candles")
