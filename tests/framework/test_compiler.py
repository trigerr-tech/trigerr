import types

from trigerr.framework.compiler import (
    compile_strategy, normalize, resolve, infer_types, infer_subscriptions, validate, lower,
    resolve_parameter_references,
)


def _sha_module():
    """ The newcomer-path example from the plan: an EOD signal feed + a spot
    clock, a two-condition entry rule, and a $-sugared exit policy. """
    module = types.SimpleNamespace()
    module.META = {"name": "SHA crossover - intraday options, down", "version": 1}
    module.PARAMETERS = {
        "sha_length": {"type": "int", "default": 25, "min": 5, "max": 200},
        "sl_percent": {"type": "float", "default": 30},
        "t1_percent": {"type": "float", "default": 1},
        "exit_policy": {"type": "choice", "default": "T1", "choices": ["T1", "T1|TSL"]},
    }
    module.FEEDS = {
        "daily": {"kind": "eod", "symbol": "$symbol", "lookback_days": 1825,
                  "indicators": {"SHA": {"length": "$sha_length", "outputs": ["sha_1", "sha_2"]}}},
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
    module.EXIT = {"policy": "$exit_policy"}
    return module


def test_normalize_reads_module_attrs_into_canonical_dict():
    ast = normalize(_sha_module())
    assert ast["clock"] == "spot"
    assert "daily" in ast["feeds"] and "spot" in ast["feeds"]
    assert ast["entry"]["when"]["op"] == "and"
    assert ast["entry"]["legs"][0]["leg_key"] == "PE"


def test_normalize_accepts_a_plain_dict_too():
    source = {"clock": "spot", "feeds": {"spot": {"kind": "intraday_candles"}},
              "entry": {"when": {"op": "lit", "value": True}, "legs": []}}
    ast = normalize(source)
    assert ast["clock"] == "spot"
    assert ast["entry"]["when"]["op"] == "lit"


def test_normalize_desugars_bare_scalars_and_param_sugar():
    source = {"entry": {"when": {"op": ">", "args": ["$threshold", 100]}, "legs": []}}
    ast = normalize(source)
    args = ast["entry"]["when"]["args"]
    assert args[0] == {"op": "param", "name": "threshold"}
    assert args[1] == {"op": "lit", "value": 100}


def test_compile_strategy_succeeds_for_the_sha_reference_example():
    plan, errors = compile_strategy(_sha_module())
    assert errors == []
    assert plan["clock"] == "spot"
    assert plan["entry"]["legs"][0]["instrument"]["selector"] == "atm_option"
    # bookkeeping keys are stripped by lower()
    assert not any(k.startswith("_") for k in plan)


def test_variables_are_inlined_by_resolve():
    source = {
        "variables": {"bull_trend": {"op": ">", "args": [{"op": "lit", "value": 2}, {"op": "lit", "value": 1}]}},
        "entry": {"when": {"op": "ref", "name": "bull_trend"}, "legs": []},
    }
    ast = resolve(normalize(source))
    # the ref to "bull_trend" has been replaced by its own expression tree
    assert ast["entry"]["when"]["op"] == ">"


def test_resolve_reports_a_variable_cycle():
    source = {
        "variables": {
            "a": {"op": "ref", "name": "b"},
            "b": {"op": "ref", "name": "a"},
        },
        "entry": {"when": {"op": "lit", "value": True}, "legs": []},
    }
    ast = resolve(normalize(source))
    assert any("cycle in variables" in e for e in ast["_errors"])


def test_resolve_orders_derived_feeds_and_reports_feed_cycles():
    feeds = {
        "spot": {"kind": "intraday_candles"},
        "m15": {"derive": "spot", "transform": "resample"},
        "ha15": {"derive": "m15", "transform": "heikin_ashi"},
    }
    ast = resolve(normalize({"feeds": feeds, "entry": {"when": {"op": "lit", "value": True}, "legs": []}}))
    assert ast["_feed_order"].index("spot") < ast["_feed_order"].index("m15") < ast["_feed_order"].index("ha15")

    cyclic_feeds = {"a": {"derive": "b"}, "b": {"derive": "a"}}
    ast_cyclic = resolve(normalize({"feeds": cyclic_feeds,
                                    "entry": {"when": {"op": "lit", "value": True}, "legs": []}}))
    assert any("cycle in feeds" in e for e in ast_cyclic["_errors"])


def test_infer_types_flags_unknown_op():
    source = {"entry": {"when": {"op": "not_a_real_op", "args": []}, "legs": []}}
    ast = infer_types(resolve(normalize(source)))
    assert any("unknown op" in e for e in ast["_errors"])


def test_infer_types_rejects_boolean_where_number_expected():
    source = {"entry": {"when": {"op": ">", "args": [{"op": "lit", "value": True}, {"op": "lit", "value": 1}]},
                        "legs": []}}
    ast = infer_types(resolve(normalize(source)))
    assert any("expects Number, got Boolean" in e for e in ast["_errors"])


def test_infer_types_rejects_number_where_series_expected():
    # "rising" needs the raw history, not an already-coerced scalar
    source = {"entry": {"when": {"op": "rising", "args": [{"op": "lit", "value": 5}]}, "legs": []}}
    ast = infer_types(resolve(normalize(source)))
    assert any("expects Series, got Number" in e for e in ast["_errors"])


def test_infer_subscriptions_collects_feed_refs_and_native_reads_and_clock():
    source = {
        "clock": "spot",
        "feeds": {"spot": {}, "daily": {}, "breadth": {}},
        "entry": {"when": {"op": "and", "args": [
            {"op": "ref", "name": "sha_1", "ctx": {"feed": "daily"}},
            {"op": "native", "plugin": "ml", "reads": ["breadth"], "type": "Boolean", "args": []},
        ]}, "legs": []},
    }
    ast = normalize(source)
    subs = infer_subscriptions(ast)
    assert subs == {"spot", "daily", "breadth"}


def test_validate_flags_missing_clock_and_undeclared_feed():
    source = {"entry": {"when": {"op": "ref", "name": "x", "ctx": {"feed": "ghost"}}, "legs": []}}
    ast = infer_types(resolve(normalize(source)))
    errors = validate(ast)
    assert any("no clock feed" in e for e in errors)
    assert any("ghost" in e for e in errors)


def test_validate_flags_duplicate_leg_keys():
    source = {
        "clock": "spot", "feeds": {"spot": {}},
        "entry": {"when": {"op": "lit", "value": True},
                  "legs": [{"leg_key": "CE"}, {"leg_key": "CE"}]},
    }
    ast = infer_types(resolve(normalize(source)))
    assert any("duplicate leg_key: CE" in e for e in validate(ast))


def test_validate_flags_lookahead_offset():
    source = {
        "clock": "spot", "feeds": {"spot": {}},
        "entry": {"when": {"op": "ref", "name": "close", "ctx": {"feed": "spot", "offset": 1}}, "legs": []},
    }
    ast = infer_types(resolve(normalize(source)))
    assert any("lookahead" in e for e in validate(ast))


def test_validate_flags_native_reading_undeclared_feed_and_plugin():
    source = {
        "clock": "spot", "feeds": {"spot": {}},
        "entry": {"when": {"op": "native", "plugin": "ml", "reads": ["ghost_feed"],
                           "type": "Boolean", "args": []}, "legs": []},
        "native_plugins": {},
    }
    ast = infer_types(resolve(normalize(source)))
    errors = validate(ast)
    assert any("undeclared plugin: ml" in e for e in errors)
    assert any("undeclared feed: ghost_feed" in e for e in errors)


def test_validate_flags_exit_rule_targeting_undeclared_leg():
    source = {
        "clock": "spot", "feeds": {"spot": {}},
        "entry": {"when": {"op": "lit", "value": True}, "legs": [{"leg_key": "CE"}]},
        "exit": {"rules": [{"condition": "stoploss_hit", "exit_type": "SL", "legs": "PE"}]},
    }
    ast = infer_types(resolve(normalize(source)))
    assert any("targets undeclared leg: PE" in e for e in validate(ast))


def test_validate_skips_leg_targeting_check_when_legs_are_decided_at_runtime():
    """ A plugin using the check_entry_condition escape hatch never declares
    ENTRY.legs in the AST - its exit rules must not be flagged as targeting
    "undeclared" legs just because none are declared statically. """
    source = {
        "clock": "spot", "feeds": {"spot": {}},
        "entry": {"when": None, "legs": []},
        "exit": {"rules": [{"condition": "stoploss_hit", "exit_type": "SL", "legs": "PE"}]},
    }
    ast = infer_types(resolve(normalize(source)))
    assert validate(ast) == []


def test_resolve_parameter_references_substitutes_nested_dollar_strings():
    block = {"condition": "spot_moved_percent", "percent": "$spot_sl_percent",
             "nested": {"threshold": "$other"}, "list": ["$other", 5]}
    result = resolve_parameter_references(block, {"spot_sl_percent": 2.5, "other": 10})
    assert result["percent"] == 2.5
    assert result["nested"]["threshold"] == 10
    assert result["list"] == [10, 5]
