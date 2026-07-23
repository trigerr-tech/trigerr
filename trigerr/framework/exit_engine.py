""" The shared exit engine: evaluates an ordered trigger table per candle and
returns per-leg exit decisions. Generalizes strat_strdl_eios's policy_triggers
design; legacy single-leg exit_policy strings ("T1", "T1|TSL", ...) compile to
equivalent trigger tables so migrated strategies behave identically.

A trigger is a plain dict: {"condition": <name>, "exit_type": <level>,
"legs": <key|list|"ALL">} plus whatever params that condition needs. Unlike
the first cut of this module, **every condition takes its parameters from the
trigger dict, never from a hardcoded global ctx key** — this is what lets one
strategy hold two spot-move rules at different thresholds, and what gives a
UI slider something to bind to. $name values are expected to already be
resolved (see compiler.resolve_parameter_references) by the time a trigger
reaches evaluate_exit_triggers.

EXIT_CONDITIONS is a registry of {name: function} in the same style as
apply_indicators — adding a condition costs one function + one entry.
REQUIRES declares the ctx/leg keys each condition needs, so a harness can
validate a compiled table once at startup and fail loud on a missing key
instead of silently evaluating False forever (the MARKETEXIT defect this
module exists to prevent from recurring). """

import datetime


def _is_long(leg):
    return leg["position_type"] == "LONG"


# ---------------------------------------------------------------------------
# Condition functions — each takes (leg, ctx, trigger) and returns True when
# the trigger fires for that leg.
#   `leg` is the plain leg-state dict: candle, position_type, entry_price,
#         entry_time, sl_price, trailing_sl, t1_price, t2_price, t3_price,
#         liquidation_price
#   `ctx` carries shared state: spot_candle, candle_time, market_exit_time,
#         entry_spot, parameters (resolved), legs
# ---------------------------------------------------------------------------

def check_stoploss_hit(leg, ctx, trigger):
    """ Fixed stop-loss: close beyond sl_price against the position """
    close = leg["candle"]["close"]
    return close <= leg["sl_price"] if _is_long(leg) else close >= leg["sl_price"]


def check_trailing_stoploss_hit(leg, ctx, trigger):
    """ Trailing stop-loss: close beyond trailing_sl against the position """
    close = leg["candle"]["close"]
    return close <= leg["trailing_sl"] if _is_long(leg) else close >= leg["trailing_sl"]


def check_liquidation_stop_hit(leg, ctx, trigger):
    """ Liquidation stop (crypto): liquidation price inside the candle range """
    liquidation_price = leg.get("liquidation_price")
    if not liquidation_price:
        return False
    return leg["candle"]["low"] <= liquidation_price <= leg["candle"]["high"]


def check_target_hit(leg, ctx, trigger):
    """ Target hit: close beyond t1/t2/t3 price in the position's favor. The
    trigger's exit_type ("T1"/"T2"/"T3") picks which target price. """
    close = leg["candle"]["close"]
    target_price = leg[f"{trigger['exit_type'].lower()}_price"]
    if target_price is None:
        return False
    return close >= target_price if _is_long(leg) else close <= target_price


def check_market_square_off_reached(leg, ctx, trigger):
    """ Time-based square-off at market exit time """
    market_exit_time = ctx.get("market_exit_time")
    if market_exit_time is None or ctx.get("candle_time") is None:
        return False
    return ctx["candle_time"] >= market_exit_time


def check_stale_position_timeout(leg, ctx, trigger):
    """ Positional timeout: held >= timeout_threshold days and underwater
    (sha_eod's STEXIT — long-only semantics kept exactly as legacy) """
    entry_time = leg.get("entry_time")
    if entry_time is None:
        return False
    elapsed_days = (leg["candle"]["timestamp"] - entry_time).total_seconds() / 86400
    timeout_threshold = trigger.get("timeout_threshold", 15)
    return elapsed_days >= timeout_threshold and leg["candle"]["close"] < leg["entry_price"]


def check_spot_moved_percent(leg, ctx, trigger):
    """ Spot moved N percent from entry spot (straddle-style, direction-aware).
    "percent" is read from the trigger, not a hardcoded ctx key — two spot
    rules at different thresholds can coexist in one strategy. """
    spot = ctx["spot_candle"]["close"]
    entry_spot = ctx["entry_spot"]
    move_pct = (spot - entry_spot) / entry_spot * 100
    threshold = trigger["percent"]
    direction = trigger.get("direction", "EITHER")
    if direction == "UP":
        return move_pct >= threshold
    if direction == "DOWN":
        return move_pct <= -threshold
    return abs(move_pct) >= threshold


def check_spot_moved_points(leg, ctx, trigger):
    """ Spot moved N points from entry spot (straddle-style, direction-aware) """
    move = ctx["spot_candle"]["close"] - ctx["entry_spot"]
    threshold = trigger["points"]
    direction = trigger.get("direction", "EITHER")
    if direction == "UP":
        return move >= threshold
    if direction == "DOWN":
        return move <= -threshold
    return abs(move) >= threshold


def check_option_premium_moved_percent(leg, ctx, trigger):
    """ Short-premium leg moved N percent from its entry premium. SL fires when
    premium RISES against the short; T1 when it DECAYS in the short's favor.
    "measure_leg" (defaulting to the trigger's own "legs") picks whose premium
    is measured. """
    measured = trigger.get("measure_leg", trigger.get("legs", "ALL"))
    target_leg = leg if measured == "ALL" else ctx["legs"].get(measured)
    if target_leg is None:
        return False
    price = target_leg["candle"]["close"]
    entry_price = target_leg["entry_price"]
    if trigger["exit_type"] == "SL":
        return (price - entry_price) / entry_price * 100 >= trigger["sl_percent"]
    return (entry_price - price) / entry_price * 100 >= trigger["t1_percent"]


def check_combined_pnl_percent(leg, ctx, trigger):
    """ Combined short-premium P&L as percent of total entry premium (straddle-wide) """
    legs = ctx["legs"]
    combined_entry = sum(l["entry_price"] for l in legs.values())
    combined_pnl = sum(l["entry_price"] - l["candle"]["close"] for l in legs.values())
    combined_pnl_pct = combined_pnl / combined_entry * 100
    if trigger["exit_type"] == "SL":
        return combined_pnl_pct <= -trigger["loss_percent"]
    return combined_pnl_pct >= trigger["profit_percent"]


EXIT_CONDITIONS = {
    "stoploss_hit": check_stoploss_hit,
    "trailing_stoploss_hit": check_trailing_stoploss_hit,
    "liquidation_stop_hit": check_liquidation_stop_hit,
    "target_hit": check_target_hit,
    "market_square_off_reached": check_market_square_off_reached,
    "stale_position_timeout": check_stale_position_timeout,
    "spot_moved_percent": check_spot_moved_percent,
    "spot_moved_points": check_spot_moved_points,
    "option_premium_moved_percent": check_option_premium_moved_percent,
    "combined_pnl_percent": check_combined_pnl_percent,
}

# Declares the ctx/leg keys each condition reads — a harness validates a
# compiled table's triggers against this once at startup and aborts on a
# missing key, rather than silently evaluating False forever.
REQUIRES = {
    "stoploss_hit": ["candle", "position_type", "sl_price"],
    "trailing_stoploss_hit": ["candle", "position_type", "trailing_sl"],
    "liquidation_stop_hit": ["candle", "liquidation_price"],
    "target_hit": ["candle", "position_type"],
    "market_square_off_reached": ["market_exit_time", "candle_time"],
    "stale_position_timeout": ["entry_time", "entry_price"],
    "spot_moved_percent": ["spot_candle", "entry_spot"],
    "spot_moved_points": ["spot_candle", "entry_spot"],
    "option_premium_moved_percent": ["legs"],
    "combined_pnl_percent": ["legs"],
}


def evaluate_exit_triggers(ctx, triggers):
    """ Evaluates the ordered trigger list against every leg in ctx["legs"].
    Returns {leg_key: [exit_type, ...]} — an ordered, de-duplicated list of
    exit levels per leg (multiple levels can fire on one candle; the executor
    splits quantity across them exactly like the legacy per-strategy loops
    did). """
    decisions = {leg_key: [] for leg_key in ctx["legs"]}
    for trigger in triggers:
        condition_fn = EXIT_CONDITIONS[trigger["condition"]]
        target = trigger.get("legs", "ALL")
        for leg_key, leg in ctx["legs"].items():
            if target != "ALL" and leg_key not in (target if isinstance(target, list) else [target]):
                continue
            if trigger["exit_type"] in decisions[leg_key]:
                continue
            if condition_fn(leg, ctx, trigger):
                decisions[leg_key].append(trigger["exit_type"])
    return decisions


# ---------------------------------------------------------------------------
# Legacy exit_policy compiler — single-leg strategies keep passing the same
# exit_policy strings they always have; each compiles to an equivalent trigger
# table plus the order_exit_levels / target_split / sl_split dicts that
# calculate_exit_quantity and convert_to_trades already expect.
# ---------------------------------------------------------------------------

_BASE_SL_SPLIT = {"SL": 1.0, "TSL": 1.0, "LSL": 1.0, "MARKETEXIT": 1.0, "STEXIT": 1.0}

_POLICY_TABLE = {
    "T1": {
        "triggers": [
            {"condition": "market_square_off_reached", "exit_type": "MARKETEXIT"},
            {"condition": "liquidation_stop_hit", "exit_type": "LSL"},
            {"condition": "stoploss_hit", "exit_type": "SL"},
            {"condition": "target_hit", "exit_type": "T1"},
            {"condition": "stale_position_timeout", "exit_type": "STEXIT"},
        ],
        "order_exit_levels": ["SL", "TSL", "LSL", "MARKETEXIT", "T1", "STEXIT"],
        "target_split": {"T1": 1, "T2": 0, "T3": 0},
    },
    "T1|TSL": {
        "triggers": [
            {"condition": "market_square_off_reached", "exit_type": "MARKETEXIT"},
            {"condition": "liquidation_stop_hit", "exit_type": "LSL"},
            {"condition": "stoploss_hit", "exit_type": "SL"},
            {"condition": "target_hit", "exit_type": "T1"},
            {"condition": "trailing_stoploss_hit", "exit_type": "TSL"},
        ],
        "order_exit_levels": ["SL", "TSL", "LSL", "MARKETEXIT", "STEXIT"],
        "target_split": {"T1": 0.5, "T2": 0.5, "T3": 0.0},
    },
    "T1|T2": {
        "triggers": [
            {"condition": "market_square_off_reached", "exit_type": "MARKETEXIT"},
            {"condition": "liquidation_stop_hit", "exit_type": "LSL"},
            {"condition": "stoploss_hit", "exit_type": "SL"},
            {"condition": "target_hit", "exit_type": "T1"},
            {"condition": "target_hit", "exit_type": "T2"},
        ],
        "order_exit_levels": ["SL", "TSL", "LSL", "MARKETEXIT", "T2", "STEXIT"],
        "target_split": {"T1": 0.5, "T2": 0.5, "T3": 0.0},
    },
    "T1|T2|T3": {
        "triggers": [
            {"condition": "market_square_off_reached", "exit_type": "MARKETEXIT"},
            {"condition": "liquidation_stop_hit", "exit_type": "LSL"},
            {"condition": "stoploss_hit", "exit_type": "SL"},
            {"condition": "target_hit", "exit_type": "T1"},
            {"condition": "target_hit", "exit_type": "T2"},
            {"condition": "target_hit", "exit_type": "T3"},
        ],
        "order_exit_levels": ["SL", "TSL", "LSL", "MARKETEXIT", "T3", "STEXIT"],
        "target_split": {"T1": 0.5, "T2": 0.25, "T3": 0.25},
    },
}

_FALLBACK_POLICY = {
    "triggers": [
        {"condition": "market_square_off_reached", "exit_type": "MARKETEXIT"},
        {"condition": "liquidation_stop_hit", "exit_type": "LSL"},
        {"condition": "stoploss_hit", "exit_type": "SL"},
        {"condition": "trailing_stoploss_hit", "exit_type": "TSL"},
    ],
    "order_exit_levels": ["SL", "TSL", "LSL", "MARKETEXIT", "STEXIT"],
    "target_split": {"T1": 0, "T2": 0, "T3": 0},
}


def compile_exit_policy_to_triggers(exit_policy):
    """ Compiles a legacy exit_policy string into {triggers, order_exit_levels,
    target_split, sl_split}. Unknown policies get the legacy else-branch
    (TSL-only) behavior, same as every strat file's trailing else. """
    policy = _POLICY_TABLE.get(exit_policy, _FALLBACK_POLICY)
    return {
        "triggers": list(policy["triggers"]),
        "order_exit_levels": list(policy["order_exit_levels"]),
        "target_split": dict(policy["target_split"]),
        "sl_split": dict(_BASE_SL_SPLIT),
    }


def calculate_target_and_stoploss_prices(entry_price, position_type, t1_percent, sl_percent):
    """ The standard t1/t2/t3/sl ladder every single-leg strategy computes at
    entry — one implementation instead of the copy in every strat file. """
    if position_type == "LONG":
        return {
            "t1_price": round(entry_price + (entry_price * t1_percent) / 100, 2),
            "sl_price": round(entry_price - (entry_price * sl_percent) / 100, 2),
            "t2_price": round(entry_price + (entry_price * (2 * t1_percent)) / 100, 2),
            "t3_price": round(entry_price + (entry_price * (3 * t1_percent)) / 100, 2),
        }
    return {
        "t1_price": round(entry_price - (entry_price * t1_percent) / 100, 2),
        "sl_price": round(entry_price + (entry_price * sl_percent) / 100, 2),
        "t2_price": round(entry_price - (entry_price * (2 * t1_percent)) / 100, 2),
        "t3_price": round(entry_price - (entry_price * (3 * t1_percent)) / 100, 2),
    }


def validate_exit_triggers(triggers):
    """ Fail-loud check: every trigger's condition must be a known name. Used
    by a harness at startup (Phase 3) before any order is placed. Returns a
    list of readable problems; empty means the table is safe to run. """
    errors = []
    for trigger in triggers:
        condition = trigger.get("condition")
        if condition not in EXIT_CONDITIONS:
            errors.append(f"unknown exit condition: {condition}")
    return errors


# Keys the platform actually guarantees to have set by the time exits are
# evaluated — build_strategy_context always sets the ctx-level ones;
# place_entry_order_for_leg always sets the leg-level ones once a leg enters.
GUARANTEED_CTX_KEYS = {"market_exit_time", "candle_time", "spot_candle", "entry_spot", "legs"}
GUARANTEED_LEG_KEYS = {"candle", "position_type", "sl_price", "trailing_sl",
                       "entry_time", "entry_price", "liquidation_price"}


def validate_exit_requirements_satisfiable(triggers):
    """ Fail-loud check (Decision #6): beyond validate_exit_triggers's "is
    this a known condition name", every REQUIRES key the compiled triggers
    declare must be something the platform actually guarantees to populate —
    not merely assumed to be there. This is the direct fix for the original
    defect: ctx["market_exit_time"] was never set, so MARKETEXIT silently
    evaluated False forever; here, a condition needing an unguaranteed key is
    caught at startup, before any order is placed, instead of failing silent
    mid-position. """
    errors = validate_exit_triggers(triggers)
    for trigger in triggers:
        condition = trigger.get("condition")
        for key in REQUIRES.get(condition, []):
            if key not in GUARANTEED_CTX_KEYS and key not in GUARANTEED_LEG_KEYS:
                errors.append(f"condition '{condition}' requires '{key}', which nothing guarantees to set")
    return errors
