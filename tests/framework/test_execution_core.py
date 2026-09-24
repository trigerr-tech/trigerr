import datetime
import types

import trigerr.framework.execution_core as ec


WIDE_OPEN_PRICING = {day: [{"start_price": 0, "end_price": 10 ** 9}]
                     for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}


class _ExpiryMap:
    """ Just the hget the instrument resolver needs. """

    def hget(self, key, field):
        return {"current": "2026-08-27", "near": "2026-09-24"}.get(field)


class FakeState:
    def __init__(self):
        self.orders = []
        self.lt_calls = []
        self.poll_script = []
        self.alerts = []
        self.saved_vt_trades = []
        self.saved_lt_trades = []
        self.live_candles = {}
        self.recent_candles = {}
        self.investment_updates = []
        self.order_cursors = []


STATE_CURSOR = object()


def _base_ctx(state, mode="vt", legs=None):
    return {
        "mode": mode, "logger": types.SimpleNamespace(warning=lambda *a, **k: None, exception=lambda *a, **k: None,
                                                       info=lambda *a, **k: None),
        "plugin_file": "strat_test", "app_db_cursor": None,
        # Derivative legs resolve their channel from the expiry map the
        # collector publishes, so a leg cannot be built without one.
        "rdb_cursor": _ExpiryMap(),
        # Orders and request status live in the tenant's state Redis, apart
        # from market data; a plain sentinel, since the order sinks are stubbed.
        "state_cursor": STATE_CURSOR,
        "user_id": "u1", "strategy_id": "s1", "request_id": "r1", "credential_id": "c1",
        "symbol": "NIFTY", "underlying": "NIFTY", "market": "IN", "exchange": "XNSE",
        "symbols_dict": {"strike_difference": 50, "lot_size": 25, "max_qpo": 1800},
        "lot_size": 25, "broker": "zerodha",
        "market_config": {"entry_pricing": WIDE_OPEN_PRICING},
        "market_exit_time": datetime.time(15, 30),
        "investment": 100000, "sizing": {"sizer": "capital_with_leverage", "leverage": 1},
        "parameters": {"t1_percent": 1, "sl_percent": 30, "order_type": "MARKET"},
        "legs": legs or {}, "feeds": {"spot": []}, "clock_feed": "spot",
        "exit_rules": {"triggers": [], "order_exit_levels": ["SL", "TSL", "LSL", "MARKETEXIT", "T1", "STEXIT"],
                      "target_split": {"T1": 1, "T2": 0, "T3": 0},
                      "sl_split": {"SL": 1.0, "TSL": 1.0, "LSL": 1.0, "MARKETEXIT": 1.0, "STEXIT": 1.0}},
        "orders_list": [], "market_type": "options", "c_index": 0,
        "create_alert": lambda **k: state.alerts.append(k),
        "update_investment": lambda **k: state.investment_updates.append(k),
        "plugin": types.SimpleNamespace(),
    }


def _patch_order_sinks(monkeypatch, state):
    def fake_place_vt_order(order_candle, quantity, quantity_left, position_type, transaction_type,
                            exit_type, trade_action, **kwargs):
        order = {"tradingsymbol": order_candle.get("symbol"), "quantity": quantity,
                 "quantity_left": quantity_left, "position_type": position_type,
                 "transaction_type": transaction_type, "exit_type": exit_type, "trade_action": trade_action,
                 "order_timestamp": datetime.datetime(2026, 1, 1, 9, 20)}
        order.update(kwargs.get("params") or {})
        state.orders.append(order)
        state.order_cursors.append(kwargs.get("redis_cursor"))
        return list(state.orders)

    def fake_place_lt_order(**kwargs):
        state.lt_calls.append(kwargs)
        return "success", {"order_id": f"OID{len(state.lt_calls)}"}

    def fake_poll_order_status(**kwargs):
        if state.poll_script:
            return state.poll_script.pop(0)
        return "success", {"average_price": 100.0, "timestamp": datetime.datetime(2026, 1, 1, 9, 20, 5)}

    def fake_save_lt_order(orders_list, symbol, quantity, quantity_left, params, **kwargs):
        order = {"tradingsymbol": symbol, "quantity": quantity, "quantity_left": quantity_left}
        order.update(params or {})
        state.orders.append(order)
        return "success", list(state.orders)

    def fake_fetch_orders_list(redis_cursor, request_id):
        return list(state.orders)

    def fake_check_existing_order(symbol, exit_type, orders_list, entry_time):
        return any(o.get("tradingsymbol") == symbol and o.get("exit_type") == exit_type for o in orders_list)

    def fake_convert_to_trades(orders_list, **kwargs):
        if any(o.get("trade_action") == "EXIT" for o in orders_list):
            return [{"pnl": 5.0, "net_pnl": 4.5}]
        return []

    monkeypatch.setattr(ec, "place_vt_order", fake_place_vt_order)
    monkeypatch.setattr(ec, "place_lt_order", fake_place_lt_order)
    monkeypatch.setattr(ec, "poll_order_status", fake_poll_order_status)
    monkeypatch.setattr(ec, "save_lt_order", fake_save_lt_order)
    monkeypatch.setattr(ec, "fetch_orders_list", fake_fetch_orders_list)
    monkeypatch.setattr(ec, "check_existing_order", fake_check_existing_order)
    monkeypatch.setattr(ec, "convert_to_trades", fake_convert_to_trades)
    monkeypatch.setattr(ec, "save_vt_trade", lambda **k: state.saved_vt_trades.append(k))
    monkeypatch.setattr(ec, "save_lt_trade", lambda **k: state.saved_lt_trades.append(k))
    monkeypatch.setattr(ec, "fetch_live_candle", lambda redis_cursor, symbol: state.live_candles.get(symbol))
    monkeypatch.setattr(ec, "fetch_recent_candle", lambda redis_cursor, symbol: state.recent_candles.get(symbol))
    monkeypatch.setattr(ec, "fetch_available_funds", lambda credential_id: 500000)
    monkeypatch.setattr(ec, "calculate_funds", lambda investment, available_funds: min(investment, available_funds))


def _pe_leg(leg_key="PE"):
    return {"leg_key": leg_key, "side": "BUY", "instrument": {"selector": "atm_option", "option_type": "PE"}}


def _candle(close, minute=20, symbol="NIFTY_23450_PE_2026-08-27"):
    """ enter_legs re-resolves every leg, so the seeded key must be the channel
    the resolver produces -- which now carries the contract's own expiry. """
    return {"symbol": symbol, "timestamp": datetime.datetime(2026, 1, 1, 9, minute),
            "open": close, "high": close + 1, "low": close - 1, "close": close}


# ---------------------------------------------------------------------------
# build_leg_order_params
# ---------------------------------------------------------------------------

def test_build_leg_order_params_is_leg_scoped():
    ctx = _base_ctx(FakeState())
    leg = {"leg_key": "PE", "entry_price": 100, "sl_price": 70, "t1_price": 101,
           "option_type": "PE", "strike_price": 23450}
    params = ec.build_leg_order_params(ctx, leg)
    assert params["leg_key"] == "PE"
    assert params["entry_price"] == 100
    assert params["strike_price"] == 23450


# ---------------------------------------------------------------------------
# place_entry_order_for_leg
# ---------------------------------------------------------------------------

def test_place_entry_order_for_leg_vt_success(monkeypatch):
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    ctx = _base_ctx(state, mode="vt")
    state.live_candles["NIFTY_23450_PE_2026-08-27"] = _candle(100)
    state.recent_candles["NIFTY_23450_PE_2026-08-27"] = _candle(100)

    leg = {"leg_key": "PE", "side": "BUY", "instrument": {"selector": "atm_option", "option_type": "PE"},
          "exit_symbol": "NIFTY_23450_PE_2026-08-27", "strike_price": 23450, "option_type": "PE",
          "lot_size": 25, "position_type": "LONG", "transaction_type": "BUY", "order_exchange": "NFO"}

    assert ec.place_entry_order_for_leg(ctx, leg) is True
    assert leg["entry_price"] == 100
    assert leg["sl_price"] == 70
    assert leg["t1_price"] == 101
    assert leg["leg_key"] in ctx["legs"]
    assert leg["order_params"]["leg_key"] == "PE"
    assert state.orders[-1]["trade_action"] == "ENTRY"


def test_vt_entry_order_goes_to_the_state_cursor_not_the_market_data_one(monkeypatch):
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    ctx = _base_ctx(state, mode="vt")
    state.live_candles["NIFTY_23450_PE_2026-08-27"] = _candle(100)
    state.recent_candles["NIFTY_23450_PE_2026-08-27"] = _candle(100)
    leg = {"leg_key": "PE", "side": "BUY", "instrument": {"selector": "atm_option", "option_type": "PE"},
           "exit_symbol": "NIFTY_23450_PE_2026-08-27", "strike_price": 23450, "option_type": "PE",
           "lot_size": 25, "position_type": "LONG", "transaction_type": "BUY", "order_exchange": "NFO"}

    assert ec.place_entry_order_for_leg(ctx, leg) is True
    assert state.order_cursors == [STATE_CURSOR]


def test_place_entry_order_for_leg_vt_fails_without_live_candle(monkeypatch):
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    ctx = _base_ctx(state, mode="vt")
    leg = {"leg_key": "PE", "exit_symbol": "NIFTY_23450_PE_2026-08-27", "lot_size": 25,
          "position_type": "LONG", "transaction_type": "BUY", "order_exchange": "NFO"}
    assert ec.place_entry_order_for_leg(ctx, leg) is False
    assert state.orders == []


def test_place_entry_order_for_leg_rejects_outside_pricing_window(monkeypatch):
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    ctx = _base_ctx(state, mode="vt")
    ctx["market_config"]["entry_pricing"] = {
        day: [{"start_price": 0, "end_price": 0}]  # nothing is ever in-window
        for day in WIDE_OPEN_PRICING}
    state.live_candles["NIFTY_23450_PE_2026-08-27"] = _candle(100)
    leg = {"leg_key": "PE", "exit_symbol": "NIFTY_23450_PE_2026-08-27", "lot_size": 25,
          "position_type": "LONG", "transaction_type": "BUY", "order_exchange": "NFO"}
    assert ec.place_entry_order_for_leg(ctx, leg) is False


def test_place_entry_order_for_leg_lt_success_polls_then_saves(monkeypatch):
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    ctx = _base_ctx(state, mode="lt")
    state.live_candles["NIFTY_23450_PE_2026-08-27"] = _candle(100)
    state.recent_candles["NIFTY_23450_PE_2026-08-27"] = _candle(100)

    leg = {"leg_key": "PE", "exit_symbol": "NIFTY_23450_PE_2026-08-27", "lot_size": 25,
          "position_type": "LONG", "transaction_type": "BUY", "order_exchange": "NFO",
          "option_type": "PE", "strike_price": 23450}
    assert ec.place_entry_order_for_leg(ctx, leg) is True
    assert leg["entry_price"] == 100.0  # from the scripted poll response
    assert state.lt_calls[0]["symbol"] == "NIFTY_23450_PE_2026-08-27"
    assert state.lt_calls[0]["transaction_type"] == "BUY"


def test_place_entry_order_for_leg_lt_alerts_on_placement_failure(monkeypatch):
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    monkeypatch.setattr(ec, "place_lt_order", lambda **k: ("error", {"message": "rejected"}))
    ctx = _base_ctx(state, mode="lt")
    state.live_candles["NIFTY_23450_PE_2026-08-27"] = _candle(100)
    state.recent_candles["NIFTY_23450_PE_2026-08-27"] = _candle(100)
    leg = {"leg_key": "PE", "exit_symbol": "NIFTY_23450_PE_2026-08-27", "lot_size": 25,
          "position_type": "LONG", "transaction_type": "BUY", "order_exchange": "NFO"}
    assert ec.place_entry_order_for_leg(ctx, leg) is False
    assert len(state.alerts) == 1
    assert "Live Order Error" in state.alerts[0]["title"]


def test_place_entry_order_for_leg_lt_alerts_on_polling_failure(monkeypatch):
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    state.poll_script = [("failed", {"message": "timeout"})]
    ctx = _base_ctx(state, mode="lt")
    state.live_candles["NIFTY_23450_PE_2026-08-27"] = _candle(100)
    state.recent_candles["NIFTY_23450_PE_2026-08-27"] = _candle(100)
    leg = {"leg_key": "PE", "exit_symbol": "NIFTY_23450_PE_2026-08-27", "lot_size": 25,
          "position_type": "LONG", "transaction_type": "BUY", "order_exchange": "NFO"}
    assert ec.place_entry_order_for_leg(ctx, leg) is False
    assert any("Entry Polling Error" in a["title"] for a in state.alerts)


# ---------------------------------------------------------------------------
# enter_legs — defect #4 (multi-leg entry safety)
# ---------------------------------------------------------------------------

SPOT_CANDLE = _candle(23456, symbol="NIFTY")  # -> ATM strike 23450 (strike_difference=50)


def test_enter_legs_all_fill(monkeypatch):
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    ctx = _base_ctx(state, mode="vt")
    ctx["feeds"]["spot"] = [SPOT_CANDLE]
    state.live_candles["NIFTY_23450_CE_2026-08-27"] = _candle(50, symbol="NIFTY_23450_CE_2026-08-27")
    state.live_candles["NIFTY_23450_PE_2026-08-27"] = _candle(45, symbol="NIFTY_23450_PE_2026-08-27")
    state.recent_candles["NIFTY_23450_CE_2026-08-27"] = _candle(50, symbol="NIFTY_23450_CE_2026-08-27")
    state.recent_candles["NIFTY_23450_PE_2026-08-27"] = _candle(45, symbol="NIFTY_23450_PE_2026-08-27")

    legs = [{"leg_key": "CE", "side": "SELL", "instrument": {"selector": "atm_option", "option_type": "CE"}},
            {"leg_key": "PE", "side": "SELL", "instrument": {"selector": "atm_option", "option_type": "PE"}}]
    assert ec.enter_legs(ctx, legs) == "entered"
    assert set(ctx["legs"]) == {"CE", "PE"}


def test_enter_legs_total_miss_is_retry_not_abort(monkeypatch):
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    ctx = _base_ctx(state, mode="vt")
    ctx["feeds"]["spot"] = [SPOT_CANDLE]
    # no live candles at all -> every leg fails to place, nothing filled
    legs = [_pe_leg()]
    assert ec.enter_legs(ctx, legs) == "retry"
    assert state.alerts == []
    assert ctx["legs"] == {}


def test_enter_legs_partial_fill_unwinds_and_aborts(monkeypatch):
    """ Defect #4: one leg fills, the other fails to find live data -> the
    filled leg must be unwound, not left as a naked position. """
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    ctx = _base_ctx(state, mode="vt")
    ctx["feeds"]["spot"] = [SPOT_CANDLE]
    state.live_candles["NIFTY_23450_CE_2026-08-27"] = _candle(50, symbol="NIFTY_23450_CE_2026-08-27")
    state.recent_candles["NIFTY_23450_CE_2026-08-27"] = _candle(50, symbol="NIFTY_23450_CE_2026-08-27")
    # PE has no live candle -> its entry fails

    legs = [{"leg_key": "CE", "side": "SELL", "instrument": {"selector": "atm_option", "option_type": "CE"}},
            {"leg_key": "PE", "side": "SELL", "instrument": {"selector": "atm_option", "option_type": "PE"}}]
    assert ec.enter_legs(ctx, legs) == "abort"
    # CE filled then got unwound (a MANUAL exit order), PE never entered
    assert "PE" not in ctx["legs"]
    manual_exits = [o for o in state.orders if o.get("exit_type") == "MANUAL"]
    assert len(manual_exits) == 1
    assert any("Partial Leg Entry" in a["title"] for a in state.alerts)
    assert any("Leg Unwind" in a["title"] for a in state.alerts)


# ---------------------------------------------------------------------------
# place_exit_order_for_leg / convert_leg_orders_to_trade — defect #3
# ---------------------------------------------------------------------------

def _entered_leg(leg_key, entry_price=100, quantity=10):
    return {"leg_key": leg_key, "tradingsymbol": f"SYM_{leg_key}", "exit_symbol": f"SYM_{leg_key}",
           "position_type": "LONG",
           "quantity": quantity, "quantity_left": quantity, "entry_price": entry_price,
           "sl_price": 70, "trailing_sl": 70, "t1_price": 101, "t2_price": None, "t3_price": None,
           "entry_time": datetime.datetime(2026, 1, 1, 9, 20), "lot_size": 25, "order_exchange": "NFO",
           "liquidation_price": None,
           "order_params": {"leg_key": leg_key, "entry_price": entry_price}}


def test_place_exit_order_for_leg_does_not_convert_to_trade_until_all_legs_flat(monkeypatch):
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    ctx = _base_ctx(state, mode="vt")
    ctx["legs"] = {"CE": _entered_leg("CE"), "PE": _entered_leg("PE")}

    ec.place_exit_order_for_leg(ctx, ctx["legs"]["CE"], "T1", _candle(101))
    assert ctx["legs"]["CE"]["quantity_left"] == 0
    assert state.saved_vt_trades == []  # PE is still open - no trade booked yet

    ec.place_exit_order_for_leg(ctx, ctx["legs"]["PE"], "T1", _candle(101))
    assert ctx["legs"]["PE"]["quantity_left"] == 0
    # now that both are flat - once per leg (legacy's convert_straddle_trades
    # saves one trade record per leg too, each stamped with the combined pnl)
    assert len(state.saved_vt_trades) == 2


def test_place_exit_order_for_leg_uses_this_legs_own_order_params(monkeypatch):
    """ Defect #2: exiting one leg must not read another leg's params off a
    shared ctx slot. """
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    ctx = _base_ctx(state, mode="vt")
    ce_leg = _entered_leg("CE", entry_price=50)
    pe_leg = _entered_leg("PE", entry_price=45)
    ctx["legs"] = {"CE": ce_leg, "PE": pe_leg}

    ec.place_exit_order_for_leg(ctx, ce_leg, "T1", _candle(51))
    ce_order = state.orders[-1]
    assert ce_order["entry_price"] == 50  # CE's own, not PE's 45

    ec.place_exit_order_for_leg(ctx, pe_leg, "T1", _candle(46))
    pe_order = state.orders[-1]
    assert pe_order["entry_price"] == 45


def test_place_exit_order_for_leg_skips_an_already_placed_exit_level(monkeypatch):
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    ctx = _base_ctx(state, mode="vt")
    leg = _entered_leg("PE")
    ctx["legs"] = {"PE": leg}
    ctx["orders_list"] = [{"tradingsymbol": "SYM_PE", "exit_type": "T1"}]
    ec.place_exit_order_for_leg(ctx, leg, "T1", _candle(101))
    assert leg["quantity_left"] == 10  # unchanged - check_existing_order short-circuited


def test_convert_leg_orders_to_trade_skips_after_a_manual_exit(monkeypatch):
    state = FakeState()
    state.orders = [{"trade_action": "EXIT", "exit_type": "MANUAL"}]
    _patch_order_sinks(monkeypatch, state)
    ctx = _base_ctx(state, mode="vt")
    ec.convert_leg_orders_to_trade(ctx)
    assert state.saved_vt_trades == []


# ---------------------------------------------------------------------------
# rebuild_legs_from_open_orders — defect #3 (restart collision)
# ---------------------------------------------------------------------------

def test_rebuild_legs_prefers_explicit_leg_key_over_option_type():
    ctx = _base_ctx(FakeState(), mode="vt")
    # two CE legs (e.g. a ratio spread) - option_type alone would collide
    open_orders = {
        "SYM_CE1": {"leg_key": "CE_short", "option_type": "CE", "position_type": "SHORT",
                   "quantity_left": 10, "trigger_price": 50, "order_timestamp": "2026-01-01 09:20:00"},
        "SYM_CE2": {"leg_key": "CE_long", "option_type": "CE", "position_type": "LONG",
                   "quantity_left": 5, "trigger_price": 60, "order_timestamp": "2026-01-01 09:20:00"},
    }
    ec.rebuild_legs_from_open_orders(ctx, open_orders)
    assert set(ctx["legs"]) == {"CE_short", "CE_long"}
    assert ctx["legs"]["CE_short"]["tradingsymbol"] == "SYM_CE1"
    assert ctx["legs"]["CE_long"]["tradingsymbol"] == "SYM_CE2"


def test_rebuild_legs_falls_back_to_option_type_when_no_leg_key_saved():
    ctx = _base_ctx(FakeState(), mode="vt")
    open_orders = {"SYM_PE": {"option_type": "PE", "position_type": "LONG", "quantity_left": 10,
                              "trigger_price": 45, "order_timestamp": "2026-01-01 09:20:00"}}
    ec.rebuild_legs_from_open_orders(ctx, open_orders)
    assert "PE" in ctx["legs"]


def test_rebuild_legs_calls_plugin_on_restart_hook():
    """ rebuild_legs_from_open_orders only ports the generic leg shape (task
    #93) - a plugin that stashed its own state onto the order via
    params_extra (a custom exit ladder, a TSL plugin's db_order_id) restores
    it via an on_restart(ctx, leg, order) hook, called once per rebuilt leg
    after the generic leg dict is built. """
    calls = []

    class Plugin:
        def on_restart(self, ctx, leg, order):
            calls.append((leg["leg_key"], order["custom_field"]))
            leg["custom_field"] = order["custom_field"]

    ctx = _base_ctx(FakeState(), mode="vt")
    ctx["plugin"] = Plugin()
    open_orders = {"SYM_CE": {"leg_key": "CE", "option_type": "CE", "position_type": "LONG",
                              "quantity_left": 10, "trigger_price": 50,
                              "order_timestamp": "2026-01-01 09:20:00", "custom_field": 42}}
    ec.rebuild_legs_from_open_orders(ctx, open_orders)
    assert calls == [("CE", 42)]
    assert ctx["legs"]["CE"]["custom_field"] == 42


def test_rebuild_legs_without_plugin_or_on_restart_does_not_crash():
    """ Most plugins (eios, straddle, dummy...) declare no on_restart -
    the hook must be optional, matching every other escape-hatch function's
    getattr(plugin, name, None) contract. """
    ctx = _base_ctx(FakeState(), mode="vt")
    ctx["plugin"] = types.SimpleNamespace()  # no on_restart attribute
    open_orders = {"SYM_CE": {"leg_key": "CE", "option_type": "CE", "position_type": "LONG",
                              "quantity_left": 10, "trigger_price": 50,
                              "order_timestamp": "2026-01-01 09:20:00"}}
    ec.rebuild_legs_from_open_orders(ctx, open_orders)
    assert "CE" in ctx["legs"]

    ctx2 = _base_ctx(FakeState(), mode="vt")  # no ctx["plugin"] key at all
    ec.rebuild_legs_from_open_orders(ctx2, open_orders)
    assert "CE" in ctx2["legs"]


# ---------------------------------------------------------------------------
# apply_compounding_to_investment
# ---------------------------------------------------------------------------

def test_apply_compounding_increases_investment_on_a_winning_trade(monkeypatch):
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    ctx = _base_ctx(state, mode="vt")
    ctx["parameters"].update(apply_compounding=True, compounding_factor=1,
                            max_investment=1000000, initial_investment=100000, reinvest_cutoff=1000)
    state.orders = [{"trade_action": "EXIT"}]
    ec.apply_compounding_to_investment(ctx)
    assert ctx["investment"] == 100004.5  # 100000 + 4.5 net_pnl
    assert ctx["sizing"]["investment"] == ctx["investment"]


def test_apply_compounding_is_a_noop_when_not_enabled():
    ctx = _base_ctx(FakeState(), mode="vt")
    ctx["parameters"]["apply_compounding"] = False
    ec.apply_compounding_to_investment(ctx)
    assert ctx["investment"] == 100000


# ---------------------------------------------------------------------------
# wait_for_entry_signal / monitor_open_position
# ---------------------------------------------------------------------------

def _plan_with_entry(when, legs):
    return {"clock": "spot", "entry": {"when": when, "legs": legs}}


def test_wait_for_entry_signal_uses_the_compiled_entry_rule(monkeypatch):
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    ctx = _base_ctx(state, mode="vt")
    state.live_candles["NIFTY_23450_PE_2026-08-27"] = _candle(100, symbol="NIFTY_23450_PE_2026-08-27")
    state.recent_candles["NIFTY_23450_PE_2026-08-27"] = _candle(100, symbol="NIFTY_23450_PE_2026-08-27")

    when = {"op": ">", "args": [{"op": "ref", "name": "close", "ctx": {"feed": "spot"}}, {"op": "lit", "value": 23000}]}
    ctx["plan"] = _plan_with_entry(when, [_pe_leg()])
    ctx["plugin"] = types.SimpleNamespace()
    ctx["tick_source"] = iter([(datetime.datetime(2026, 1, 1, 9, 20), {"spot": [SPOT_CANDLE]})])

    assert ec.wait_for_entry_signal(ctx) is True
    assert "PE" in ctx["legs"]


def test_wait_for_entry_signal_prefers_check_entry_condition_escape_hatch(monkeypatch):
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    ctx = _base_ctx(state, mode="vt")
    state.live_candles["NIFTY_23450_PE_2026-08-27"] = _candle(100, symbol="NIFTY_23450_PE_2026-08-27")
    state.recent_candles["NIFTY_23450_PE_2026-08-27"] = _candle(100, symbol="NIFTY_23450_PE_2026-08-27")

    ctx["plan"] = _plan_with_entry(None, [])
    ctx["plugin"] = types.SimpleNamespace(check_entry_condition=lambda c: [_pe_leg()])
    ctx["tick_source"] = iter([(datetime.datetime(2026, 1, 1, 9, 20), {"spot": [SPOT_CANDLE]})])

    assert ec.wait_for_entry_signal(ctx) is True


def test_wait_for_entry_signal_respects_should_trade_today_guard():
    ctx = _base_ctx(FakeState(), mode="vt")
    ctx["plan"] = _plan_with_entry({"op": "lit", "value": True}, [_pe_leg()])
    ctx["plugin"] = types.SimpleNamespace(check_should_trade_today=lambda c: False)
    ctx["tick_source"] = iter([(datetime.datetime(2026, 1, 1, 9, 20), {"spot": [_candle(100)]})])
    assert ec.wait_for_entry_signal(ctx) is False


def test_wait_for_entry_signal_stops_at_market_close_with_no_signal():
    ctx = _base_ctx(FakeState(), mode="vt")
    ctx["plan"] = _plan_with_entry({"op": "lit", "value": False}, [])
    ctx["plugin"] = types.SimpleNamespace()
    ctx["tick_source"] = iter([(datetime.datetime(2026, 1, 1, 15, 31), {"spot": [_candle(100)]})])
    assert ec.wait_for_entry_signal(ctx) is False


def test_monitor_open_position_exits_and_stops_when_all_legs_flat(monkeypatch):
    state = FakeState()
    _patch_order_sinks(monkeypatch, state)
    ctx = _base_ctx(state, mode="vt")
    leg = _entered_leg("PE")
    ctx["legs"] = {"PE": leg}
    ctx["exit_rules"]["triggers"] = [{"condition": "target_hit", "exit_type": "T1"}]

    exit_candle = _candle(105)
    ctx["tick_source"] = iter([(datetime.datetime(2026, 1, 1, 9, 21), {"spot": [exit_candle]})])
    state.recent_candles["SYM_PE"] = exit_candle

    ec.monitor_open_position(ctx)
    assert leg["quantity_left"] == 0
    assert len(state.saved_vt_trades) == 1
