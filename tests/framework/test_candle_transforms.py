import datetime

from trigerr.framework.candle_transforms import CANDLE_TRANSFORMS


def _candles(closes, start_minute=0):
    # "symbol" is required: change_granularity's no-symbol-column branch has a
    # pre-existing bug (compares the sentinel against 0 instead of "") that
    # raises a KeyError on a symbol-less frame - flagged to Anurag separately,
    # not fixed here since trigerr/utils.py is shared SDK code out of scope
    # for this change. Every real candle in this codebase already carries a
    # "symbol" key, so this sidesteps it rather than working around a bug.
    base = datetime.datetime(2026, 1, 1, 9, 0)
    return [{"symbol": "NIFTY", "timestamp": base + datetime.timedelta(minutes=start_minute + i),
             "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 100}
            for i, c in enumerate(closes)]


def test_heikin_ashi_produces_the_expected_first_open():
    rows = _candles([10, 12, 11])
    out = CANDLE_TRANSFORMS["heikin_ashi"]["apply"](rows, {})
    # SDK's convert_candle_pattern: first HA open = (open[0] + close[0]) / 2
    assert out[0]["open"] == (rows[0]["open"] + rows[0]["close"]) / 2
    assert len(out) == 3


def test_heikin_ashi_empty_is_a_noop():
    assert CANDLE_TRANSFORMS["heikin_ashi"]["apply"]([], {}) == []


def test_resample_collapses_to_the_declared_granularity():
    rows = _candles([10, 11, 12, 13, 14, 15])  # 6 one-minute candles
    out = CANDLE_TRANSFORMS["resample"]["apply"](rows, {"granularity": 3})
    assert len(out) == 2
    assert out[0]["open"] == 10
    assert out[0]["close"] == 12
    assert out[0]["high"] == 13  # rows[2]["high"] = 12+1


def test_merge_doji_folds_inside_candles():
    base = datetime.datetime(2026, 1, 1, 9, 0)
    rows = [
        {"timestamp": base, "open": 10, "high": 15, "low": 5, "close": 12, "volume": 100},
        # entirely inside [10, 12] body of the previous candle -> merges
        {"timestamp": base + datetime.timedelta(minutes=1), "open": 10.5, "high": 11, "low": 10.2, "close": 11.5,
         "volume": 50},
        # clearly outside -> stays separate
        {"timestamp": base + datetime.timedelta(minutes=2), "open": 20, "high": 22, "low": 19, "close": 21,
         "volume": 50},
    ]
    out = CANDLE_TRANSFORMS["merge_doji"]["apply"](rows, {})
    assert len(out) == 2
    assert out[0]["high"] == 15
    assert out[0]["low"] == 5
    assert out[0]["volume"] == 150
    assert out[1]["close"] == 21


def test_slope_angle_is_zero_for_a_flat_line_and_positive_for_a_rise():
    flat = _candles([10, 10, 10, 10])
    out = CANDLE_TRANSFORMS["slope_angle"]["apply"](flat, {"length": 3, "column": "close"})
    assert out[:3] == [dict(c, slope_angle=None) for c in flat[:3]]
    assert out[3]["slope_angle"] == 0.0

    rising = _candles([10, 11, 12, 20])
    out_rising = CANDLE_TRANSFORMS["slope_angle"]["apply"](rising, {"length": 3, "column": "close"})
    assert out_rising[3]["slope_angle"] > 0
