import datetime

from trigerr.framework.exit_engine import (
    EXIT_CONDITIONS, REQUIRES, evaluate_exit_triggers, compile_exit_policy_to_triggers,
    calculate_target_and_stoploss_prices, validate_exit_triggers, validate_exit_requirements_satisfiable,
)


def _long_leg(**overrides):
    leg = {"position_type": "LONG", "candle": {"close": 100, "low": 99, "high": 101},
           "sl_price": 90, "trailing_sl": 92, "t1_price": 110, "t2_price": None, "t3_price": None,
           "entry_price": 100, "entry_time": datetime.datetime(2026, 1, 1, 9, 20),
           "liquidation_price": None}
    leg.update(overrides)
    return leg


def test_check_stoploss_hit_long_and_short():
    leg = _long_leg(candle={"close": 89, "low": 88, "high": 90})
    assert EXIT_CONDITIONS["stoploss_hit"](leg, {}, {}) is True

    short_leg = _long_leg(position_type="SHORT", sl_price=110, candle={"close": 111, "low": 109, "high": 112})
    assert EXIT_CONDITIONS["stoploss_hit"](short_leg, {}, {}) is True


def test_check_target_hit_reads_exit_type_specific_price():
    leg = _long_leg(candle={"close": 115, "low": 114, "high": 116})
    trigger = {"exit_type": "T1"}
    assert EXIT_CONDITIONS["target_hit"](leg, {}, trigger) is True


def test_check_market_square_off_reached_requires_both_keys():
    leg = _long_leg()
    assert EXIT_CONDITIONS["market_square_off_reached"](leg, {}, {}) is False
    ctx = {"market_exit_time": datetime.time(15, 30), "candle_time": datetime.time(15, 31)}
    assert EXIT_CONDITIONS["market_square_off_reached"](leg, ctx, {}) is True


def test_spot_moved_percent_reads_threshold_from_trigger_not_ctx():
    """ The defect this rework fixes: two spot-move rules at different
    thresholds must both work in the same strategy, which is impossible if
    the threshold comes from one hardcoded ctx["inputs"] key. """
    ctx = {"spot_candle": {"close": 102}, "entry_spot": 100}
    leg = _long_leg()
    tight_trigger = {"percent": 1, "direction": "EITHER", "exit_type": "SL"}
    loose_trigger = {"percent": 5, "direction": "EITHER", "exit_type": "SL"}
    assert EXIT_CONDITIONS["spot_moved_percent"](leg, ctx, tight_trigger) is True
    assert EXIT_CONDITIONS["spot_moved_percent"](leg, ctx, loose_trigger) is False


def test_option_premium_moved_percent_reads_percents_from_trigger():
    ctx = {"legs": {"CE": _long_leg(entry_price=50, candle={"close": 70, "low": 69, "high": 71})}}
    trigger = {"exit_type": "SL", "sl_percent": 30, "measure_leg": "CE"}
    assert EXIT_CONDITIONS["option_premium_moved_percent"](_long_leg(), ctx, trigger) is True
    trigger_loose = {"exit_type": "SL", "sl_percent": 50, "measure_leg": "CE"}
    assert EXIT_CONDITIONS["option_premium_moved_percent"](_long_leg(), ctx, trigger_loose) is False


def test_every_condition_has_a_requires_declaration():
    for name in EXIT_CONDITIONS:
        assert name in REQUIRES, f"{name} has no REQUIRES declaration"


def test_evaluate_exit_triggers_deduplicates_per_leg_and_respects_leg_targeting():
    ctx = {
        "legs": {"CE": _long_leg(candle={"close": 89, "low": 88, "high": 90}),
                 "PE": _long_leg(candle={"close": 115, "low": 114, "high": 116})},
    }
    triggers = [
        {"condition": "stoploss_hit", "exit_type": "SL", "legs": "CE"},
        {"condition": "target_hit", "exit_type": "T1", "legs": "PE"},
    ]
    decisions = evaluate_exit_triggers(ctx, triggers)
    assert decisions == {"CE": ["SL"], "PE": ["T1"]}


def test_compile_exit_policy_to_triggers_known_and_unknown_policy():
    t1 = compile_exit_policy_to_triggers("T1")
    assert t1["target_split"] == {"T1": 1, "T2": 0, "T3": 0}
    assert {t["condition"] for t in t1["triggers"]} <= set(EXIT_CONDITIONS)

    fallback = compile_exit_policy_to_triggers("not-a-real-policy")
    assert fallback["order_exit_levels"] == ["SL", "TSL", "LSL", "MARKETEXIT", "STEXIT"]


def test_calculate_target_and_stoploss_prices_long_and_short():
    long_prices = calculate_target_and_stoploss_prices(100, "LONG", t1_percent=1, sl_percent=30)
    assert long_prices["t1_price"] == 101
    assert long_prices["sl_price"] == 70

    short_prices = calculate_target_and_stoploss_prices(100, "SHORT", t1_percent=1, sl_percent=30)
    assert short_prices["t1_price"] == 99
    assert short_prices["sl_price"] == 130


def test_validate_exit_triggers_catches_unknown_condition():
    errors = validate_exit_triggers([{"condition": "not_a_condition", "exit_type": "SL"}])
    assert any("unknown exit condition" in e for e in errors)
    assert validate_exit_triggers([{"condition": "stoploss_hit", "exit_type": "SL"}]) == []


def test_every_built_in_policys_triggers_pass_the_requirements_gate():
    """ The fail-loud gate must not be a false-positive tripwire on any of the
    built-in exit_policy tables — every REQUIRES key they declare really is
    something build_strategy_context/place_entry_order_for_leg guarantees. """
    for exit_policy in ("T1", "T1|TSL", "T1|T2", "T1|T2|T3", "unknown-falls-back"):
        triggers = compile_exit_policy_to_triggers(exit_policy)["triggers"]
        assert validate_exit_requirements_satisfiable(triggers) == []


def test_validate_exit_requirements_satisfiable_catches_an_unguaranteed_key():
    triggers = [{"condition": "market_square_off_reached", "exit_type": "MARKETEXIT"}]
    # Simulate a hypothetical condition needing something nothing sets.
    original = dict(REQUIRES)
    REQUIRES["market_square_off_reached"] = ["market_exit_time", "nonexistent_key"]
    try:
        errors = validate_exit_requirements_satisfiable(triggers)
    finally:
        REQUIRES["market_square_off_reached"] = original["market_square_off_reached"]
    assert any("nonexistent_key" in e for e in errors)
