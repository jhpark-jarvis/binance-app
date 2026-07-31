from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Candle:
    symbol: str
    interval: str
    open_time: int
    close_time: int
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    quote_volume: Decimal
    trade_count: int
    is_closed: bool
    source_event_time: int | None


@dataclass(frozen=True)
class Trade:
    symbol: str
    aggregate_trade_id: int
    event_time: int
    trade_time: int
    price: Decimal
    quantity: Decimal
    first_trade_id: int
    last_trade_id: int
    is_buyer_maker: bool
