import datetime

import trigerr.framework.data_feeds as data_feeds
from trigerr.framework.data_feeds import DATA_FEED_KINDS, resolve_feeds
from trigerr.framework.compiler import normalize


def _candles(closes, start_minute=0):
    # see test_candle_transforms._candles for why "symbol" is required
    base = datetime.datetime(2026, 1, 1, 9, 0)
    return [{"symbol": "NIFTY",
             "timestamp": (base + datetime.timedelta(minutes=start_minute + i)).strftime("%Y-%m-%d %H:%M:%S"),
             "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 100}
            for i, c in enumerate(closes)]


def test_fetch_eod_uses_lookback_window_and_declared_exchange(monkeypatch):
    captured = {}

    def fake_fetch_eod_candles(symbol, start_date, end_date, exchange):
        captured.update(symbol=symbol, start_date=start_date, end_date=end_date, exchange=exchange)
        return []

    monkeypatch.setattr(data_feeds, "fetch_eod_candles", fake_fetch_eod_candles)
    ctx = {"as_of_date": datetime.date(2026, 1, 10), "parameters": {}}
    feed_spec = {"symbol": "NIFTY", "lookback_days": 5, "exchange": "XNSE"}
    DATA_FEED_KINDS["eod"]["fetch_historical"](feed_spec, ctx)

    assert captured["symbol"] == "NIFTY"
    assert captured["start_date"] == datetime.date(2026, 1, 5)
    assert captured["end_date"] == datetime.date(2026, 1, 10)
    assert captured["exchange"] == "XNSE"


def test_fetch_eod_applies_declared_indicators(monkeypatch):
    rows = _candles([100, 102, 101, 105, 110, 103, 99, 98, 97, 96,
                      95, 94, 93, 92, 91, 90, 89, 88, 87, 86,
                      85, 84, 83, 82, 81, 80, 79, 78, 77, 76])

    monkeypatch.setattr(data_feeds, "fetch_eod_candles",
                        lambda symbol, start_date, end_date, exchange: rows)
    ctx = {"parameters": {}}
    feed_spec = {"symbol": "NIFTY", "indicators": {"SHA": {"length": 5}}}
    result = DATA_FEED_KINDS["eod"]["fetch_historical"](feed_spec, ctx)

    assert "sha_1" in result[-1] and "sha_2" in result[-1]


def test_fetch_intraday_candles_futures_options_call_the_right_underlying_fetcher(monkeypatch):
    calls = {}
    monkeypatch.setattr(data_feeds, "fetch_index_candles",
                        lambda **kw: calls.setdefault("intraday", kw) or [])
    monkeypatch.setattr(data_feeds, "fetch_futures_candle",
                        lambda **kw: calls.setdefault("futures", kw) or [])
    monkeypatch.setattr(data_feeds, "fetch_option_candles",
                        lambda **kw: calls.setdefault("options", kw) or [])

    ctx = {"parameters": {}}
    DATA_FEED_KINDS["intraday_candles"]["fetch_historical"]({"symbol": "NIFTY", "granularity": 5}, ctx)
    DATA_FEED_KINDS["futures"]["fetch_historical"]({"symbol": "NIFTY"}, ctx)
    DATA_FEED_KINDS["options"]["fetch_historical"](
        {"symbol": "NIFTY", "option_type": "PE", "strike_price": 100}, ctx)

    assert calls["intraday"]["symbol"] == "NIFTY" and calls["intraday"]["granularity"] == 5
    assert calls["futures"]["underlying"] == "NIFTY"
    assert calls["options"]["option_type"] == "PE" and calls["options"]["strike_price"] == 100


def test_mongo_collection_and_pickled_model_read_from_ctx():
    ctx = {"collections": {"nse_pre_open": [{"advances": 10, "declines": 5}]},
           "models": {"models/sha_model.pkl": "the-loaded-model-object"}}
    assert DATA_FEED_KINDS["mongo_collection"]["fetch_historical"]({"name": "nse_pre_open"}, ctx) == \
        [{"advances": 10, "declines": 5}]
    assert DATA_FEED_KINDS["pickled_model"]["fetch_historical"]({"path": "models/sha_model.pkl"}, ctx) == \
        "the-loaded-model-object"


def test_resolve_feeds_substitutes_params_and_orders_derived_after_base(monkeypatch):
    rows = _candles([10, 11, 12, 13, 14, 15])
    captured_symbol = {}

    def fake_fetch_index_candles(symbol, start_date, end_date, granularity, exchange):
        captured_symbol["symbol"] = symbol
        return rows

    monkeypatch.setattr(data_feeds, "fetch_index_candles", fake_fetch_index_candles)

    ast = normalize({
        "feeds": {
            "spot": {"kind": "intraday_candles", "symbol": "$symbol", "granularity": 1},
            "m15": {"derive": "spot", "transform": "resample", "granularity": 3},
        },
    })
    ctx = {"parameters": {"symbol": "NIFTY"}}
    feeds = resolve_feeds(ast, ctx)

    assert captured_symbol["symbol"] == "NIFTY"
    assert len(feeds["spot"]) == 6
    assert len(feeds["m15"]) == 2  # resampled 6 one-minute candles into 2 three-minute bars


def test_resolve_feeds_chains_resample_then_heikin_ashi(monkeypatch):
    """ Gate 3: an m1 -> m15(resample) -> ha15(heikin_ashi) chain should match
    what change_granularity + convert_candle_pattern would produce directly. """
    rows = _candles([10, 12, 11, 13, 15, 14])
    monkeypatch.setattr(data_feeds, "fetch_index_candles", lambda **kw: rows)

    ast = normalize({
        "feeds": {
            "spot": {"kind": "intraday_candles", "symbol": "NIFTY"},
            "m3": {"derive": "spot", "transform": "resample", "granularity": 3},
            "ha3": {"derive": "m3", "transform": "heikin_ashi"},
        },
    })
    feeds = resolve_feeds(ast, {"parameters": {}})

    from trigerr.utils import change_granularity, convert_candle_pattern
    import pandas as pd
    expected_m3 = change_granularity(pd.DataFrame(rows), granularity=3).to_dict("records")
    expected_ha3 = convert_candle_pattern(pd.DataFrame(expected_m3), pattern="heikin_ashi").to_dict("records")

    assert feeds["m3"] == expected_m3
    assert feeds["ha3"] == expected_ha3
