from decimal import Decimal

from app.etl.binance import BinanceMarketClient


def test_rest_kline_is_normalized_as_closed_candle() -> None:
    candle = BinanceMarketClient._candle_from_rest(
        "BTCUSDT",
        "1m",
        [
            1710000000000,
            "62000.10",
            "62010",
            "61990",
            "62005.5",
            "1.25",
            1710000059999,
            "77506",
            42,
        ],
    )

    assert candle.symbol == "BTCUSDT"
    assert candle.open_price == Decimal("62000.10")
    assert candle.trade_count == 42
    assert candle.is_closed is True


def test_websocket_payload_preserves_taker_direction_input() -> None:
    trade = BinanceMarketClient._trade_from_payload(
        {
            "a": 123,
            "p": "62000.10",
            "q": "0.004",
            "f": 100,
            "l": 102,
            "T": 1710000000100,
            "E": 1710000000110,
            "m": True,
        },
        "ETHUSDT",
    )

    assert trade.symbol == "ETHUSDT"
    assert trade.aggregate_trade_id == 123
    assert trade.price == Decimal("62000.10")
    assert trade.is_buyer_maker is True


def test_websocket_kline_marks_current_candle_as_open() -> None:
    candle = BinanceMarketClient._candle_from_stream(
        {
            "e": "kline",
            "E": 1710000000500,
            "s": "BTCUSDT",
            "k": {
                "t": 1710000000000,
                "T": 1710000059999,
                "i": "1m",
                "o": "62000",
                "h": "62001",
                "l": "61999",
                "c": "62000.5",
                "v": "0.1",
                "q": "6200",
                "n": 3,
                "x": False,
            },
        }
    )

    assert candle.is_closed is False
    assert candle.source_event_time == 1710000000500
