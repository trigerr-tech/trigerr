""" Gate 3 (data integrity) and the newcomer-path reference strategy, run
end to end: normalize -> resolve -> infer_types -> resolve_feeds -> eval_expr.
Anchored to strat_sha_eios (daily signal, spot clock) rather than strat_dummy
- the case that exposed the original harness's entry-model assumption. """
import datetime
import types

import trigerr.framework.data_feeds as data_feeds
from trigerr.framework.compiler import normalize, resolve, infer_types, validate, lower, is_lookahead_verified
from trigerr.framework.data_feeds import resolve_feeds
from trigerr.framework.expressions import eval_expr


def _sha_module():
    """ "indicators" is deliberately omitted from the daily feed here: this
    test is about the entry-rule/clock/feed CONTRACT (sha_1/sha_2 as ordinary
    feed columns), not about re-deriving the real SHA algorithm from raw OHLC
    (heikin_ashi_smoothed needs open/high/low/close, which the synthetic
    crossover fixture below doesn't carry) - that wiring is already covered by
    test_data_feeds.test_fetch_eod_applies_declared_indicators. """
    module = types.SimpleNamespace()
    module.PARAMETERS = {"symbol": {"type": "str", "default": "SBIN"},
                          "sha_length": {"type": "int", "default": 25}}
    module.FEEDS = {
        "daily": {"kind": "eod", "symbol": "$symbol", "lookback_days": 1825},
        "spot": {"kind": "intraday_candles", "symbol": "$symbol", "granularity": 1},
    }
    module.CLOCK = "spot"
    module.ENTRY = {
        "when": {"op": "and", "args": [
            {"op": "crossed_below", "args": [
                {"op": "ref", "name": "sha_2", "ctx": {"feed": "daily"}},
                {"op": "ref", "name": "sha_1", "ctx": {"feed": "daily"}}]},
            {"op": "falling", "args": [{"op": "ref", "name": "sha_2", "ctx": {"feed": "daily"}}]},
        ]},
        "legs": [{"leg_key": "PE", "side": "BUY",
                  "instrument": {"selector": "atm_option", "option_type": "PE"}}],
    }
    return module


def _compile(module):
    ast = infer_types(resolve(normalize(module)))
    errors = validate(ast)
    assert errors == [], errors
    return lower(ast)


def _daily_rows_with_a_down_crossover():
    """ sha_1 flat at 50; sha_2 above then crossing below and still falling on
    the last row - exactly legacy strat_sha_eios's DOWN entry condition. """
    base = datetime.date(2026, 1, 1)
    return [
        {"timestamp": base, "sha_1": 50, "sha_2": 55},
        {"timestamp": base + datetime.timedelta(days=1), "sha_1": 50, "sha_2": 52},
        {"timestamp": base + datetime.timedelta(days=2), "sha_1": 50, "sha_2": 45},  # crossed and falling
    ]


def test_daily_signal_plus_spot_clock_reproduces_the_sha_eios_entry_decision(monkeypatch):
    plan = _compile(_sha_module())

    monkeypatch.setattr(data_feeds, "fetch_eod_candles",
                        lambda symbol, start_date, end_date, exchange: _daily_rows_with_a_down_crossover())
    monkeypatch.setattr(data_feeds, "fetch_index_candles", lambda **kw: [])

    ctx = {"parameters": {"symbol": "SBIN", "sha_length": 25}}
    ctx["feeds"] = resolve_feeds(plan, ctx)

    decision = eval_expr(plan["entry"]["when"], ctx)
    assert decision["value"] is True


def test_no_crossover_does_not_enter():
    ctx = {"feeds": {"daily": [
        {"timestamp": datetime.date(2026, 1, 1), "sha_1": 50, "sha_2": 45},
        {"timestamp": datetime.date(2026, 1, 2), "sha_1": 50, "sha_2": 46},  # still below, not a fresh cross
    ]}}
    plan = _compile(_sha_module())
    assert eval_expr(plan["entry"]["when"], ctx)["value"] is False


def test_feeds_resolve_identically_regardless_of_mode(monkeypatch):
    """ resolve_feeds/DATA_FEED_KINDS never take a "mode" argument at all -
    structurally, bt and vt run the identical resolution for the same params. """
    rows = _daily_rows_with_a_down_crossover()
    monkeypatch.setattr(data_feeds, "fetch_eod_candles",
                        lambda symbol, start_date, end_date, exchange: rows)
    monkeypatch.setattr(data_feeds, "fetch_index_candles", lambda **kw: [])

    plan = _compile(_sha_module())
    ctx = {"parameters": {"symbol": "SBIN", "sha_length": 25}}
    feeds_first_run = resolve_feeds(plan, ctx)
    feeds_second_run = resolve_feeds(plan, ctx)
    assert feeds_first_run == feeds_second_run


def test_is_lookahead_verified_true_for_a_clean_declarative_strategy():
    ast = infer_types(resolve(normalize(_sha_module())))
    assert is_lookahead_verified(ast) is True


def test_is_lookahead_verified_false_when_a_native_node_is_present():
    source = {
        "clock": "spot", "feeds": {"spot": {}},
        "entry": {"when": {"op": "native", "plugin": "ml", "reads": [], "type": "Boolean", "args": []},
                  "legs": []},
        "native_plugins": {"ml": {"eval": lambda ctx, node: True}},
    }
    ast = infer_types(resolve(normalize(source)))
    assert is_lookahead_verified(ast) is False


def test_is_lookahead_verified_false_when_the_plugin_uses_the_escape_hatch():
    ast = infer_types(resolve(normalize(_sha_module())))
    plugin_without_hatch = types.SimpleNamespace()
    plugin_with_hatch = types.SimpleNamespace(prepare_strategy_data=lambda ctx: None)
    assert is_lookahead_verified(ast, plugin_without_hatch) is True
    assert is_lookahead_verified(ast, plugin_with_hatch) is False
