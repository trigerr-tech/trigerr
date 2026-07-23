import datetime
import types

from trigerr.framework.clock import iterate_clock_bt, evaluate_should_trade_today


def _candle(minute, close):
    return {"timestamp": datetime.datetime(2026, 1, 1, 9, minute), "close": close}


def test_iterate_clock_bt_yields_one_moment_per_clock_row_truncated_so_far():
    feeds = {
        "spot": [_candle(0, 10), _candle(1, 11), _candle(2, 12)],
        "daily": [{"timestamp": datetime.datetime(2025, 12, 31), "sha_1": 50}],
    }
    moments = list(iterate_clock_bt(feeds, "spot"))

    assert [m for m, _ in moments] == [datetime.datetime(2026, 1, 1, 9, m) for m in (0, 1, 2)]
    # at the second moment, spot only shows the first two candles - no lookahead
    _, view_at_second_moment = moments[1]
    assert [c["close"] for c in view_at_second_moment["spot"]] == [10, 11]
    # a feed with no bearing on "now" (already in the past) is untouched
    assert view_at_second_moment["daily"] == feeds["daily"]


def test_evaluate_should_trade_today_defaults_to_true_with_no_guard():
    plugin = types.SimpleNamespace()
    assert evaluate_should_trade_today({}, plugin) is True


def test_evaluate_should_trade_today_calls_the_plugin_guard():
    plugin = types.SimpleNamespace(check_should_trade_today=lambda ctx: ctx["signal_found"])
    assert evaluate_should_trade_today({"signal_found": False}, plugin) is False
    assert evaluate_should_trade_today({"signal_found": True}, plugin) is True
