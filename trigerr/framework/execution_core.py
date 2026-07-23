""" The one execution core: the only place orders get placed, polled, and
exited, for bt, vt and lt alike. Everything here calls already-pure SDK
functions (trigerr.orders.*, trigerr.data.live) that take their Mongo/Redis
cursors as parameters rather than importing a driver — so this module needs
none itself. Alerting is the one engine-owned side effect that has no pure
equivalent; it is injected as ctx["create_alert"] (bound to the real
sts_common.create_alert by the engine's build_strategy_context) rather than
imported.

Six things fixed here, inline, as the design rather than as patches:
  1. ctx["market_exit_time"] is always set by the caller (build_strategy_context)
     - MARKETEXIT can fire; this module just trusts it's there.
  2. Every leg carries its OWN order_params (leg["order_params"]) - never one
     request-scoped slot a later leg's entry would overwrite.
  3. convert_leg_orders_to_trade fires once, when EVERY leg is flat - not
     per-leg, so a straddle's first leg closing doesn't book a mixed trade.
  4. enter_legs places every leg, THEN reconciles: a total miss can retry the
     next tick; a partial fill unwinds every already-filled leg before
     stopping for the day (ports strat_strdl_eios.py's unwind).
  5. lt calls place_lt_order(symbol=...) (the real SDK signature) and threads
     max_qpo/asset_type/holding_type/order_validity throughout.
  6. rebuild_legs_from_open_orders keys legs by an explicit "leg_key" on the
     order document, not by option_type (which collided for two same-type
     legs).

One place mode still matters, on purpose: a leg's own candle for exit pricing
is fetched live (vt/lt, via fetch_recent_candle) but falls back to the clock
candle in bt, since no strike-aware historical options feed is resolved after
entry here (that would need historical option data fetched reactively once a
strike is known - out of scope; this preserves, not introduces, the original
harness's bt-side simplification for options legs). """

import datetime

from trigerr.orders.virtual import place_vt_order, save_vt_trade
from trigerr.orders.live import place_lt_order, save_lt_order, poll_order_status, save_lt_trade
from trigerr.orders.orders_utils import fetch_orders_list, convert_to_trades, check_existing_order
from trigerr.data.live import fetch_live_candle, fetch_recent_candle
from trigerr.utils import fetch_available_funds, calculate_funds, calculate_exit_quantity

from trigerr.framework.instrument import resolve_leg_to_tradable_symbol, resolve_exchange_for_leg
from trigerr.framework.position_sizing import calculate_leg_quantity
from trigerr.framework.exit_engine import evaluate_exit_triggers, calculate_target_and_stoploss_prices
from trigerr.framework.expressions import eval_expr
from trigerr.framework.clock import evaluate_should_trade_today


def _as_datetime(value):
    if isinstance(value, datetime.datetime):
        return value
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    raise ValueError(f"unrecognized timestamp: {value!r}")


def _alert(ctx, msg, title):
    ctx["logger"].exception(msg)
    ctx["create_alert"](msg=msg, title=f"{ctx['plugin_file']} {title}", file_name=ctx["plugin_file"])


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def build_leg_order_params(ctx, leg):
    """ The analysis params dict saved with every order for this leg — leg-
    scoped, not a single ctx-wide slot (defect #2). """
    params = {
        "underlying": ctx["symbol"],
        "spot_price": ctx.get("spot_price"),
        "entry_price": leg.get("entry_price"),
        "live_order_price": leg.get("entry_price"),
        "investment": ctx["investment"],
        "trailing_sl": leg.get("trailing_sl"),
        "t1_price": leg.get("t1_price"),
        "sl_price": leg.get("sl_price"),
        "t2_price": leg.get("t2_price"),
        "t3_price": leg.get("t3_price"),
        "liquidation_price": leg.get("liquidation_price"),
        "option_type": leg.get("option_type"),
        "strike_price": leg.get("strike_price"),
        "leg_key": leg["leg_key"],
    }
    params.update(leg.get("params_extra", {}))
    return params


def _entry_pricing_window_ok(ctx, price):
    today = datetime.datetime.today().strftime("%A")
    return any(slot["start_price"] <= price <= slot["end_price"]
              for slot in ctx["market_config"]["entry_pricing"][today])


def _size_leg(ctx, leg, price):
    """ vt/bt: the declared sizer, applied to ctx["investment"] directly.
    lt: the SAME declared sizer (leverage included), applied to the requested
    investment capped to real broker funds — ported from both
    strat_sha_eios's and strat_strdl_eios's lt branches, which both reuse
    their normal vt sizing formula on actual_investment rather than switching
    to a separate, leverage-free formula. A below-floor quantity means don't
    take the trade (min_quantity as a viability threshold); sizers that
    should instead floor up to it (e.g. margin_based) do so themselves. """
    inputs = ctx["parameters"]
    if ctx["mode"] != "lt":
        return calculate_leg_quantity(ctx, leg, price)

    available_funds = fetch_available_funds(credential_id=str(ctx["credential_id"]))
    if available_funds is None:
        return None
    actual_investment = calculate_funds(investment=ctx["investment"], available_funds=available_funds)

    saved_investment = ctx["investment"]
    ctx["investment"] = actual_investment
    try:
        quantity = calculate_leg_quantity(ctx, leg, price)
    finally:
        ctx["investment"] = saved_investment

    if not quantity or quantity < inputs.get("min_quantity", 1):
        return None
    return quantity


def place_entry_order_for_leg(ctx, leg):
    """ Places one leg's entry (vt or lt), sizes it, computes its target/stop
    ladder, and registers it in ctx["legs"]. Returns True on success. Does
    NOT poll for lt — enter_legs places every leg first, then reconciles
    (defect #4's ordering fix). """
    inputs = ctx["parameters"]
    rdb_cursor = ctx["rdb_cursor"]

    live_candle = fetch_live_candle(rdb_cursor, leg["exit_symbol"])
    if not live_candle:
        ctx["logger"].warning(f"No live data for {leg['exit_symbol']}")
        return False
    order_candle = fetch_recent_candle(rdb_cursor, leg["exit_symbol"]) or live_candle
    # fetch_live_candle already parses its own timestamp; fetch_recent_candle
    # (a raw Redis list read) does not - place_vt_order needs a real datetime.
    order_candle = {**order_candle, "timestamp": _as_datetime(order_candle["timestamp"])}

    if not _entry_pricing_window_ok(ctx, live_candle["close"]):
        ctx["logger"].warning(f"Entry price {live_candle['close']} outside today's pricing window")
        return False

    # Optional: strategies whose exit triggers measure moves directly off
    # entry_price (e.g. option_premium_moved_percent) rather than a fixed
    # t1/sl ladder don't declare these — validate_exit_requirements_satisfiable
    # already confirms nothing needed downstream reads t1_price/sl_price in
    # that case, so 0/0 here is a harmless, unused placeholder, not a guess.
    t1_percent = float(inputs.get("t1_percent", 0))
    sl_percent = float(inputs.get("c1_sl_percent", inputs.get("sl_percent", 0)))

    if ctx["mode"] == "vt":
        entry_price = live_candle["close"]
        leg["entry_price"] = entry_price
        leg.update(calculate_target_and_stoploss_prices(entry_price, leg["position_type"], t1_percent, sl_percent))
        leg["trailing_sl"] = leg["sl_price"]
        leg["quantity"] = _size_leg(ctx, leg, entry_price)
        if not leg["quantity"]:
            return False
        leg["quantity_left"] = leg["quantity"]
        leg["order_params"] = build_leg_order_params(ctx, leg)

        orders_list = place_vt_order(
            app_db_cursor=ctx["app_db_cursor"], redis_cursor=rdb_cursor, order_candle=order_candle,
            quantity=leg["quantity"], quantity_left=leg["quantity"], position_type=leg["position_type"],
            transaction_type=leg["transaction_type"], order_type=inputs.get("order_type", "MARKET"),
            exit_type=None, trade_action="ENTRY", lot_size=leg["lot_size"],
            user_id=ctx["user_id"], strategy_id=ctx["strategy_id"], request_id=ctx["request_id"],
            market=ctx["market"], market_type=ctx["market_type"], exchange=leg["order_exchange"],
            params=leg["order_params"])
        leg["entry_time"] = _as_datetime(orders_list[-1]["order_timestamp"])
        leg["tradingsymbol"] = orders_list[-1]["tradingsymbol"]
        ctx["orders_list"] = orders_list

    else:
        quantity = _size_leg(ctx, leg, order_candle["close"])
        if not quantity:
            ctx["logger"].warning(f"Sizing produced no quantity for {leg['exit_symbol']}")
            return False

        order_status, lt_response = place_lt_order(
            symbol=order_candle["symbol"], exchange=leg["order_exchange"], quantity=quantity,
            transaction_type=leg["transaction_type"], order_type="MARKET", lot_size=leg["lot_size"],
            credential_id=ctx["credential_id"], validity=inputs.get("order_validity", "DAY"),
            asset_type=inputs.get("asset_type", "OPTIONS"), holding_type=inputs.get("holding_type", "INTRADAY"),
            option_type=leg.get("option_type"), strike_price=leg.get("strike_price"), underlying=ctx["underlying"],
            max_qpo=ctx["symbols_dict"].get("max_qpo"))
        if order_status != "success":
            _alert(ctx, f"Error placing entry order for {leg['leg_key']}: {lt_response}", "Live Order Error")
            return False

        polling_status, live_response = poll_order_status(
            credential_id=str(ctx["credential_id"]), order_id=lt_response["order_id"],
            exchange=leg["order_exchange"], request_id=ctx["request_id"], user_id=ctx["user_id"],
            strategy_id=ctx["strategy_id"])
        if polling_status != "success":
            _alert(ctx, f"Error polling entry order for {leg['leg_key']}: {live_response}", "Entry Polling Error")
            return False

        entry_price = live_response["average_price"]
        leg["entry_price"] = entry_price
        leg.update(calculate_target_and_stoploss_prices(entry_price, leg["position_type"], t1_percent, sl_percent))
        leg["trailing_sl"] = leg["sl_price"]
        leg["quantity"] = quantity
        leg["quantity_left"] = quantity
        leg["order_params"] = build_leg_order_params(ctx, leg)

        _, orders_list = save_lt_order(
            app_db_cursor=ctx["app_db_cursor"], redis_cursor=rdb_cursor, orders_list=ctx.get("orders_list", []),
            symbol=order_candle["symbol"], quantity=quantity, quantity_left=quantity,
            position_type=leg["position_type"], transaction_type=leg["transaction_type"], trade_action="ENTRY",
            order_type="MARKET", exit_type=None, params=leg["order_params"], market_type=ctx["market_type"],
            trigger_price=entry_price, lot_size=leg["lot_size"], user_id=ctx["user_id"],
            strategy_id=ctx["strategy_id"], request_id=ctx["request_id"], exchange=leg["order_exchange"],
            exchange_timestamp=live_response["timestamp"], order_id=lt_response["order_id"],
            broker_response=live_response, option_type=leg.get("option_type"), strike_price=leg.get("strike_price"),
            underlying=ctx["underlying"], validity=inputs.get("order_validity", "DAY"),
            asset_type=inputs.get("asset_type", "OPTIONS"), holding_type=inputs.get("holding_type", "INTRADAY"),
            max_qpo=ctx["symbols_dict"].get("max_qpo"), market=ctx["market"])
        leg["entry_time"] = _as_datetime(live_response["timestamp"])
        leg["tradingsymbol"] = order_candle["symbol"]
        ctx["orders_list"] = orders_list

    ctx["legs"][leg["leg_key"]] = leg
    ctx["entry_spot"] = ctx.get("spot_price", leg["entry_price"])
    return True


def _unwind_filled_legs(ctx, filled_legs):
    """ Immediately market-exits every already-filled leg when a sibling leg
    in the same multi-leg entry failed, instead of leaving a naked position
    (ports strat_strdl_eios.py:727). """
    for leg in filled_legs:
        exit_transaction = "SELL" if leg["position_type"] == "LONG" else "BUY"
        if ctx["mode"] == "vt":
            place_vt_order(
                app_db_cursor=ctx["app_db_cursor"], redis_cursor=ctx["rdb_cursor"],
                order_candle={"symbol": leg["tradingsymbol"], "timestamp": datetime.datetime.now(),
                             "close": leg["entry_price"]},
                quantity=leg["quantity_left"], quantity_left=0, position_type=leg["position_type"],
                transaction_type=exit_transaction, order_type="MARKET", exit_type="MANUAL",
                trade_action="EXIT", lot_size=leg["lot_size"], user_id=ctx["user_id"],
                strategy_id=ctx["strategy_id"], request_id=ctx["request_id"], market=ctx["market"],
                market_type=ctx["market_type"], exchange=leg["order_exchange"], params=leg.get("order_params"))
            msg = f"Unwound {leg['leg_key']} (vt, MANUAL) after a sibling leg failed to enter."
        else:
            unwind_status, unwind_response = place_lt_order(
                symbol=leg["tradingsymbol"], exchange=leg["order_exchange"], quantity=leg["quantity_left"],
                transaction_type=exit_transaction, order_type="MARKET", lot_size=leg["lot_size"],
                credential_id=ctx["credential_id"], validity=ctx["parameters"].get("order_validity", "DAY"),
                asset_type=ctx["parameters"].get("asset_type", "OPTIONS"),
                holding_type=ctx["parameters"].get("holding_type", "INTRADAY"),
                option_type=leg.get("option_type"), strike_price=leg.get("strike_price"),
                underlying=ctx["underlying"], max_qpo=ctx["symbols_dict"].get("max_qpo"))
            msg = (f"Unwound {leg['leg_key']} ({leg['tradingsymbol']}) after a sibling leg failed: "
                  f"{unwind_status} | {unwind_response}. Verify positions manually.")
        _alert(ctx, msg, "Leg Unwind")


def enter_legs(ctx, legs):
    """ Places every leg back-to-back, THEN reconciles which filled (legacy
    multi-leg ordering) rather than stopping at the first failure. Returns:
      "entered" - every leg filled
      "retry"   - nothing filled; safe to try again on the next tick
      "abort"   - a partial fill was unwound; stop for today """
    clock_rows = ctx["feeds"][ctx["clock_feed"]]
    ctx["spot_price"] = clock_rows[-1]["close"]

    resolved_legs = []
    for leg in legs:
        resolved_leg = resolve_leg_to_tradable_symbol(ctx, dict(leg))
        resolved_leg["order_exchange"] = resolve_exchange_for_leg(ctx["exchange"], resolved_leg["instrument"]["selector"])
        resolved_legs.append(resolved_leg)

    filled, failed = [], []
    for leg in resolved_legs:
        if place_entry_order_for_leg(ctx, leg):
            filled.append(leg)
        else:
            failed.append(leg)

    if not failed:
        return "entered"
    if filled:
        _unwind_filled_legs(ctx, filled)
        _alert(ctx, f"Multi-leg entry partial fill: {[l['leg_key'] for l in filled]} filled, "
                    f"{[l['leg_key'] for l in failed]} failed — unwound.", "Partial Leg Entry")
        return "abort"
    return "retry"


def wait_for_entry_signal(ctx):
    """ Iterates ctx["tick_source"] (bt: historical replay; vt/lt: live
    ticks — both yield (moment, feeds_view)) evaluating the compiled entry
    rule, or the plugin's check_entry_condition escape hatch, until legs are
    entered, a partial multi-leg fill aborts the day, or the clock passes
    market close. Returns True once legs are entered. """
    plugin = ctx["plugin"]
    plan = ctx["plan"]
    if not evaluate_should_trade_today(ctx, plugin):
        return False

    check_entry_condition = getattr(plugin, "check_entry_condition", None)

    for moment, feeds_view in ctx["tick_source"]:
        ctx["candle_time"] = moment.time() if hasattr(moment, "time") else moment
        ctx["feeds"] = feeds_view

        if check_entry_condition:
            legs = check_entry_condition(ctx)
        else:
            legs = plan["entry"]["legs"] if eval_expr(plan["entry"]["when"], ctx)["value"] else None

        if legs:
            outcome = enter_legs(ctx, legs)
            if outcome == "entered":
                return True
            if outcome == "abort":
                return False
            # "retry": fall through to the next tick

        if ctx["market_exit_time"] and ctx["candle_time"] >= ctx["market_exit_time"]:
            return False
    return False


# ---------------------------------------------------------------------------
# Exit
# ---------------------------------------------------------------------------

def _exit_trigger_price(ctx, leg, exit_type, candle):
    if exit_type == "LSL":
        return leg["liquidation_price"]
    if exit_type == "SL" and ctx["parameters"].get("sl_trigger_at") == "sl_price":
        return leg["sl_price"]
    return candle["close"]


def _split_leg_trades(ctx, orders_list):
    """ Splits orders by leg_key (read off the orders themselves, not
    ctx["legs"] — legs may already be cleared by the time this runs) and
    converts each leg's own order flow to a trade separately —
    convert_to_trades tracks quantity_left assuming one instrument's
    chronological flow, so a multi-leg strategy's interleaved CE+PE orders
    must be split first, or its quantity tracking corrupts (ported from
    strat_strdl_eios's convert_straddle_trades). A single-leg strategy's
    orders all share one leg_key (or none), so every order already forms one
    group — lossless generalization, not new behavior for it. Returns
    {leg_key: trade_dict} once EVERY leg has a completed trade, else None. """
    leg_trades = {}
    for leg_key in {o.get("leg_key") for o in orders_list}:
        leg_orders = [o for o in orders_list if o.get("leg_key") == leg_key]
        trades = convert_to_trades(orders_list=leg_orders, market_type=ctx["market_type"],
                                   order_exit_levels=ctx["exit_rules"]["order_exit_levels"],
                                   mode=ctx["mode"], broker=ctx["broker"])
        if not trades:
            return None
        leg_trades[leg_key] = trades[-1]
    return leg_trades


def _combined_pnls(leg_trades):
    """ (gross, net) pnl summed across legs — "pnl" falls back to "net_pnl"
    for trades that don't carry a separate gross figure. For a single leg
    this reduces to that trade's own two fields, unchanged. """
    gross = sum(t.get("pnl", t["net_pnl"]) for t in leg_trades.values())
    net = sum(t["net_pnl"] for t in leg_trades.values())
    return gross, net


def convert_leg_orders_to_trade(ctx):
    """ Fires once, when EVERY leg is flat — not per leg (defect #3: the
    original _finish_leg_trade fired the moment the FIRST leg of a straddle
    closed, booking a mixed trade while the other leg was still open). Saves
    one trade record per leg (matching legacy's convert_straddle_trades),
    each stamped with the position's combined net pnl across every leg. """
    orders_list = fetch_orders_list(redis_cursor=ctx["rdb_cursor"], request_id=str(ctx["request_id"]))
    ctx["orders_list"] = orders_list
    last_order = orders_list[-1] if orders_list else None
    if last_order and last_order.get("exit_type") == "MANUAL":
        return
    leg_trades = _split_leg_trades(ctx, orders_list)
    if leg_trades is None:
        return
    _, net = _combined_pnls(leg_trades)
    for trade in leg_trades.values():
        trade["combined_pnl"] = net
        if ctx["mode"] == "vt":
            save_vt_trade(app_db_cursor=ctx["app_db_cursor"], redis_cursor=ctx["rdb_cursor"], trade_dict=trade)
        else:
            save_lt_trade(app_db_cursor=ctx["app_db_cursor"], redis_cursor=ctx["rdb_cursor"], trade_dict=trade)


def place_exit_order_for_leg(ctx, leg, exit_type, candle):
    """ Executes one exit level on one leg (vt order or lt market order),
    reading this leg's OWN order_params (defect #2) and only converting to a
    trade once ALL legs are flat (defect #3). """
    inputs = ctx["parameters"]
    exit_rules = ctx["exit_rules"]

    if check_existing_order(symbol=leg["tradingsymbol"], exit_type=exit_type,
                            orders_list=ctx["orders_list"], entry_time=leg["entry_time"]):
        return

    exit_transaction = "SELL" if leg["position_type"] == "LONG" else "BUY"
    exit_quantity = calculate_exit_quantity(total_quantity=leg["quantity_left"],
                                            target_split=exit_rules["target_split"],
                                            sl_split=exit_rules["sl_split"])[exit_type]

    if ctx["mode"] == "vt":
        leg["quantity_left"] -= exit_quantity
        ctx["orders_list"] = place_vt_order(
            app_db_cursor=ctx["app_db_cursor"], redis_cursor=ctx["rdb_cursor"], order_candle=candle,
            position_type=leg["position_type"], quantity=exit_quantity, quantity_left=leg["quantity_left"],
            transaction_type=exit_transaction, order_type=inputs.get("order_type", "MARKET"),
            exit_type=exit_type, params=leg["order_params"], lot_size=leg["lot_size"], trade_action="EXIT",
            trigger_price=_exit_trigger_price(ctx, leg, exit_type, candle),
            user_id=ctx["user_id"], strategy_id=ctx["strategy_id"], request_id=ctx["request_id"],
            market=ctx["market"], market_type=ctx["market_type"], exchange=leg["order_exchange"])

    else:
        order_status, lt_response = place_lt_order(
            symbol=leg["tradingsymbol"], exchange=leg["order_exchange"], quantity=exit_quantity,
            transaction_type=exit_transaction, order_type="MARKET", lot_size=leg["lot_size"],
            credential_id=ctx["credential_id"], validity=inputs.get("order_validity", "DAY"),
            asset_type=inputs.get("asset_type", "OPTIONS"), holding_type=inputs.get("holding_type", "INTRADAY"),
            option_type=leg.get("option_type"), strike_price=leg.get("strike_price"), underlying=ctx["underlying"],
            max_qpo=ctx["symbols_dict"].get("max_qpo"))
        if order_status != "success":
            _alert(ctx, f"Error placing exit order for {leg['leg_key']}: {lt_response}", "Live Order Error")
            return

        polling_status, live_response = poll_order_status(
            credential_id=str(ctx["credential_id"]), order_id=lt_response["order_id"],
            exchange=leg["order_exchange"], request_id=ctx["request_id"], user_id=ctx["user_id"],
            strategy_id=ctx["strategy_id"])
        if polling_status != "success":
            _alert(ctx, f"Error polling exit order for {leg['leg_key']}: {live_response}", "Exit Polling Error")
            return

        leg["quantity_left"] -= exit_quantity
        _, orders_list = save_lt_order(
            app_db_cursor=ctx["app_db_cursor"], redis_cursor=ctx["rdb_cursor"], orders_list=ctx["orders_list"],
            symbol=leg["tradingsymbol"], quantity=exit_quantity, quantity_left=leg["quantity_left"],
            position_type=leg["position_type"], transaction_type=exit_transaction, order_type="MARKET",
            exit_type=exit_type, params=leg["order_params"], market_type=ctx["market_type"], trade_action="EXIT",
            trigger_price=live_response["average_price"], lot_size=leg["lot_size"], user_id=ctx["user_id"],
            strategy_id=ctx["strategy_id"], request_id=ctx["request_id"], exchange=leg["order_exchange"],
            exchange_timestamp=live_response["timestamp"], order_id=lt_response["order_id"],
            broker_response=live_response, option_type=leg.get("option_type"), strike_price=leg.get("strike_price"),
            underlying=ctx["underlying"])
        ctx["orders_list"] = orders_list

    if all(l["quantity_left"] == 0 for l in ctx["legs"].values()):
        convert_leg_orders_to_trade(ctx)


def _refresh_leg_candles(ctx):
    clock_rows = ctx["feeds"].get(ctx["clock_feed"], [])
    clock_candle = clock_rows[-1] if clock_rows else None
    if clock_candle is not None:
        ctx["spot_candle"] = clock_candle

    for leg in ctx["legs"].values():
        if ctx["mode"] == "bt":
            leg["candle"] = clock_candle
        else:
            # fetch_recent_candle is a raw Redis list read - unlike the clock
            # feed (already normalized by tick_sources), its timestamp needs
            # parsing before any exit condition or place_vt_order sees it.
            recent = fetch_recent_candle(ctx["rdb_cursor"], leg["exit_symbol"])
            leg["candle"] = {**recent, "timestamp": _as_datetime(recent["timestamp"])} if recent else clock_candle


def monitor_open_position(ctx):
    """ Iterates ctx["tick_source"], refreshing every leg's candle, running
    the plugin's update_position_on_candle hook, evaluating exits (the
    plugin's check_exit_condition escape hatch, or the compiled trigger
    table), and executing them — until every leg is flat. """
    plugin = ctx["plugin"]
    legs = ctx["legs"]

    for moment, feeds_view in ctx["tick_source"]:
        ctx["candle_time"] = moment.time() if hasattr(moment, "time") else moment
        ctx["feeds"] = feeds_view
        _refresh_leg_candles(ctx)

        update_on_candle = getattr(plugin, "update_position_on_candle", None)
        if update_on_candle:
            update_on_candle(ctx)

        check_exit_condition = getattr(plugin, "check_exit_condition", None)
        decisions = check_exit_condition(ctx) if check_exit_condition else \
            evaluate_exit_triggers(ctx, ctx["exit_rules"]["triggers"])

        for leg_key, exit_types in decisions.items():
            leg = legs[leg_key]
            for exit_type in ([exit_types] if isinstance(exit_types, str) else exit_types or []):
                if leg["quantity_left"] > 0:
                    place_exit_order_for_leg(ctx, leg, exit_type, leg.get("candle", ctx.get("spot_candle")))

        after_exits = getattr(plugin, "after_exit_orders_placed", None)
        if after_exits:
            after_exits(ctx)

        ctx["c_index"] += 1
        if all(leg["quantity_left"] == 0 for leg in legs.values()):
            return


# ---------------------------------------------------------------------------
# Restart recovery
# ---------------------------------------------------------------------------

def rebuild_legs_from_open_orders(ctx, open_orders):
    """ Reconstructs ctx["legs"] from a previous run's open orders, keyed by
    the explicit "leg_key" persisted on each order document — not inferred
    from option_type, which collided for two same-type legs (defect #3). """
    for tradingsymbol, order in open_orders.items():
        leg_key = order.get("leg_key") or order.get("option_type") or tradingsymbol
        sl_price = order.get("trailing_sl") if ctx["mode"] == "vt" else order.get("sl_price", order.get("trailing_sl"))
        leg = {
            "leg_key": leg_key, "tradingsymbol": tradingsymbol,
            "position_type": order["position_type"],
            "transaction_type": "BUY" if order["position_type"] == "LONG" else "SELL",
            "quantity": order["quantity_left"], "quantity_left": order["quantity_left"],
            "entry_price": order["trigger_price"], "entry_time": _as_datetime(order["order_timestamp"]),
            "trailing_sl": order.get("trailing_sl"), "sl_price": sl_price,
            "t1_price": order.get("t1_price"), "t2_price": order.get("t2_price"), "t3_price": order.get("t3_price"),
            "liquidation_price": order.get("liquidation_price"), "strike_price": order.get("strike_price"),
            "option_type": order.get("option_type"),
            "lot_size": order.get("lot_size", ctx["lot_size"]),
            "order_exchange": order.get("exchange") or ctx["exchange"],
            "exit_symbol": order.get("underlying") or tradingsymbol,
            "order_params": {k: order[k] for k in ("underlying", "spot_price", "investment") if k in order},
        }
        ctx["legs"][leg_key] = leg
        if order.get("spot_price"):
            ctx["entry_spot"] = order["spot_price"]
    ctx["restarted"] = True


# ---------------------------------------------------------------------------
# Compounding
# ---------------------------------------------------------------------------

def apply_compounding_to_investment(ctx):
    """ Reads the position's combined pnl across every leg (a single leg's
    own two fields, unchanged, when there's only one) — same split as
    convert_leg_orders_to_trade, so a straddle compounds off its whole
    round's pnl (legacy's straddle_pnl), not one leg in isolation. """
    inputs = ctx["parameters"]
    if not inputs.get("apply_compounding"):
        return
    orders_list = fetch_orders_list(redis_cursor=ctx["rdb_cursor"], request_id=ctx["request_id"])
    leg_trades = _split_leg_trades(ctx, orders_list)
    if leg_trades is None:
        return
    gross, net = _combined_pnls(leg_trades)
    investment = ctx["investment"]
    if gross > 0:
        investment += net * int(inputs["compounding_factor"])
    else:
        investment += net
    if investment >= int(inputs["max_investment"]):
        investment = int(inputs["initial_investment"])
    if investment <= int(inputs["reinvest_cutoff"]):
        investment = int(inputs["initial_investment"])
    ctx["investment"] = investment
    ctx["sizing"]["investment"] = investment
    ctx["update_investment"](app_db_cursor=ctx["app_db_cursor"], redis_cursor=ctx["rdb_cursor"],
                             request_id=ctx["request_id"], mode=ctx["mode"], investment=investment)
