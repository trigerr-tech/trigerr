""" Backtest mode in the shared execution core is hermetic and fail-closed.

Until now bt had no branch anywhere in execution_core: entry, exit, unwind and trade-save all treated
"not vt" as "live", so a backtest that got past its price read would have reached place_lt_order and
the real lt_trades collection. These tests pin the replacement:

  - a whole bt round trip (entry -> exit -> trade) completes with EVERY live sink — broker orders,
    vt/lt order and trade saves, market-data reads, broker funds — patched to raise;
  - bt touches no market-data cursor (rdb_cursor is None) and only the in-memory state cursor;
  - its orders are stamped from the replayed candle, not the wall clock;
  - an unknown mode is refused at every placement site instead of falling through to live.

The vt and lt branches are covered by test_execution_core.py, which must stay green unchanged.
"""
import datetime
import types

import pytest

import trigerr.framework.execution_core as ec
from trigerr.framework.bt_state import memory_state_cursor

MONDAY = datetime.datetime(2025, 6, 2)
TUESDAY = datetime.datetime(2025, 6, 3)
ALL_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
OPEN_WINDOW = [{"start_price": 0, "end_price": 10 ** 9}]


def _candle(day, hour, minute, close):
    ts = day.replace(hour=hour, minute=minute)
    return {"timestamp": ts, "open": close, "high": close + 1, "low": close - 1, "close": close}


def _bt_ctx(mode="bt", pricing_days=ALL_DAYS, candles=None):
    alerts = []
    return {
        "mode": mode, "logger": types.SimpleNamespace(warning=lambda *a, **k: None, exception=lambda *a, **k: None,
                                                       info=lambda *a, **k: None),
        "plugin_file": "strat_bt_test", "plugin": types.SimpleNamespace(),
        # the hermetic bt state: no market-data cursor, no database, an in-memory state cursor
        "rdb_cursor": None, "app_db_cursor": None, "state_cursor": memory_state_cursor(),
        "user_id": "u1", "strategy_id": "s1", "request_id": "r1", "credential_id": None,
        "symbol": "NIFTY_50", "underlying": "NIFTY_50", "market": "IN", "exchange": "XNSE", "venue": "XNSE",
        "instrument_type": "INDEX", "data_vendor": "upstox", "broker": "zerodha",
        "symbols_dict": {"lot_size": 1, "strike_difference": 50}, "lot_size": 1,
        # real market configs list every weekday; a closed day has an empty window list
        "market_config": {"entry_pricing": {day: OPEN_WINDOW if day in pricing_days else [] for day in ALL_DAYS}},
        "market_exit_time": datetime.time(15, 30), "market_type": "spot",
        "investment": 100000, "sizing": {"sizer": "capital_with_leverage", "leverage": 1},
        "parameters": {"t1_percent": 1, "sl_percent": 30, "order_type": "MARKET"},
        "legs": {}, "orders_list": [], "c_index": 0,
        "feeds": {"spot": candles or [_candle(MONDAY, 9, 20, 100.0)]}, "clock_feed": "spot",
        "exit_rules": {"triggers": [], "order_exit_levels": ["SL", "TSL", "LSL", "MARKETEXIT", "T1", "STEXIT"],
                       "target_split": {"T1": 1, "T2": 0, "T3": 0},
                       "sl_split": {"SL": 1.0, "TSL": 1.0, "LSL": 1.0, "MARKETEXIT": 1.0, "STEXIT": 1.0}},
        "create_alert": lambda **k: alerts.append(k), "update_investment": lambda **k: None,
        "_alerts": alerts,
    }


def _spot_leg(key="SPOT", side="BUY"):
    return {"leg_key": key, "side": side, "instrument": {"selector": "spot"}}


@pytest.fixture
def live_sinks_forbidden(monkeypatch):
    """ Every way out of the process that a backtest must never use. """
    def boom(name):
        def forbidden(*args, **kwargs):
            raise AssertionError(f"a backtest reached {name}")
        return forbidden
    for name in ("place_vt_order", "place_lt_order", "save_lt_order", "poll_order_status", "save_lt_trade",
                 "save_vt_trade", "ltp", "last_candle", "fetch_available_funds"):
        monkeypatch.setattr(ec, name, boom(name))


# ---------------------------------------------------------------- the round trip

def test_bt_round_trip_completes_without_touching_any_live_sink(live_sinks_forbidden):
    ctx = _bt_ctx()
    assert ec.enter_legs(ctx, [_spot_leg()]) == "entered"

    leg = ctx["legs"]["SPOT"]
    assert leg["entry_price"] == 100.0 and leg["quantity"] and leg["tradingsymbol"]
    entry = ctx["orders_list"][-1]
    assert entry["trade_action"] == "ENTRY" and entry["leg_key"] == "SPOT"
    assert entry["data_key"].startswith("UPSTOX:XNSE:")

    exit_candle = _candle(MONDAY, 10, 5, 101.0)
    ctx["feeds"]["spot"].append(exit_candle)
    ec._refresh_leg_candles(ctx)            # bt prices every leg off the clock candle
    ec.place_exit_order_for_leg(ctx, leg, "T1", leg["candle"])

    assert leg["quantity_left"] == 0
    assert [o["trade_action"] for o in ctx["orders_list"]] == ["ENTRY", "EXIT"]
    trades = ctx["bt_trades"]
    assert len(trades) == 1
    assert trades[0]["exit_type"] == "T1" and trades[0]["pnl"] == leg["quantity"] * 1.0
    assert trades[0]["group_id"] == entry["group_id"]


def test_bt_orders_are_stamped_from_the_replayed_candle_not_the_wall_clock(live_sinks_forbidden):
    ctx = _bt_ctx(candles=[_candle(TUESDAY, 11, 40, 250.0)])
    assert ec.enter_legs(ctx, [_spot_leg()]) == "entered"
    order = ctx["orders_list"][-1]
    assert order["date"] == "2025-06-03 00:00:00" and order["order_timestamp"] == "2025-06-03 11:40:00"
    assert order["day"] == "Tuesday"
    assert order["group_id"] == "r1:2025-06-03:1"        # dated by the entry candle, not today


def test_bt_entry_pricing_window_follows_the_replayed_weekday(live_sinks_forbidden):
    ctx = _bt_ctx(pricing_days=["Monday"], candles=[_candle(TUESDAY, 9, 20, 100.0)])
    assert ec.enter_legs(ctx, [_spot_leg()]) == "retry"      # Tuesday candle, Monday-only window
    assert ctx["orders_list"] == [] and ctx["legs"] == {}


def test_bt_entries_use_only_the_in_memory_state_cursor(live_sinks_forbidden):
    ctx = _bt_ctx()
    ec.enter_legs(ctx, [_spot_leg()])
    assert ctx["state_cursor"].llen("r1_orders") == 1
    assert ctx["rdb_cursor"] is None and ctx["app_db_cursor"] is None


# ---------------------------------------------------------------- multi-leg unwind

def test_bt_partial_entry_unwinds_the_filled_leg_without_a_live_order(live_sinks_forbidden, monkeypatch):
    real_size = ec._size_leg
    monkeypatch.setattr(ec, "_size_leg", lambda ctx, leg, price: None if leg["leg_key"] == "B" else real_size(ctx, leg, price))
    ctx = _bt_ctx()
    assert ec.enter_legs(ctx, [_spot_leg("A", "BUY"), _spot_leg("B", "SELL")]) == "abort"
    actions = [(o["leg_key"], o["trade_action"], o["exit_type"]) for o in ctx["orders_list"]]
    assert ("A", "ENTRY", "None") in actions and ("A", "EXIT", "MANUAL") in actions
    assert any("Unwound A (bt, MANUAL)" in a["msg"] for a in ctx["_alerts"])


# ---------------------------------------------------------------- refusals

def test_manual_exit_is_refused_in_a_backtest(live_sinks_forbidden):
    ctx = _bt_ctx()
    ec.enter_legs(ctx, [_spot_leg()])
    result = ec.manual_exit_legs(ctx, {"SPOT": 100.0})
    assert result["exited"] == [] and "not available in a backtest" in result["refused"]["SPOT"]
    assert ctx["legs"]["SPOT"]["quantity_left"] > 0


def test_a_derivative_leg_fails_closed_in_bt_until_historical_pricing_exists(live_sinks_forbidden):
    """ Option/futures contracts resolve from the live expiry map in market-data Redis, which a
    backtest does not have. It must stop with a clear error, not read live state or guess. Replace
    this test when historical option pricing lands (plan slice P2). """
    ctx = _bt_ctx()
    with pytest.raises(KeyError, match="rdb_cursor"):
        ec.enter_legs(ctx, [{"leg_key": "CE", "side": "BUY",
                             "instrument": {"selector": "atm_option", "option_type": "CE"}}])
    assert ctx["orders_list"] == []


@pytest.mark.parametrize("site", ["entry", "exit", "convert", "manual", "unwind"])
def test_an_unknown_mode_is_refused_at_every_placement_site(live_sinks_forbidden, site):
    ctx = _bt_ctx()
    ec.enter_legs(ctx, [_spot_leg()])                   # a real open position to act on
    leg = ctx["legs"]["SPOT"]
    if site == "convert":                               # needs a completed round trip to reach the save
        ec.place_exit_order_for_leg(ctx, leg, "T1", {**ctx["feeds"]["spot"][-1], "close": 101.0})
    ctx["mode"] = "backtest-typo"
    calls = {
        "entry": lambda: ec.place_entry_order_for_leg(ctx, {**_spot_leg(), "exit_symbol": "X", "data_key": "k",
                                                            "lot_size": 1, "position_type": "LONG",
                                                            "transaction_type": "BUY", "order_exchange": "NSE"}),
        "exit": lambda: ec.place_exit_order_for_leg(ctx, leg, "T1", ctx["feeds"]["spot"][-1]),
        "convert": lambda: ec.convert_leg_orders_to_trade(ctx),
        "manual": lambda: ec.manual_exit_legs(ctx, {"SPOT": 100.0}),
        "unwind": lambda: ec._unwind_filled_legs(ctx, [leg]),
    }
    with pytest.raises(ValueError, match="unknown mode"):
        calls[site]()
