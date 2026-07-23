import datetime

from trigerr.framework.expressions import eval_expr, is_compatible, EXPRESSION_OPS, NUMBER, SERIES, BOOLEAN


def _ref(name, feed):
    return {"op": "ref", "name": name, "ctx": {"feed": feed}}


def _ctx(feeds, parameters=None, clock_time=None):
    return {"feeds": feeds, "parameters": parameters or {}, "clock_time": clock_time}


def test_lit_and_arithmetic():
    node = {"op": "+", "args": [{"op": "lit", "value": 2}, {"op": "lit", "value": 3}]}
    assert eval_expr(node, _ctx({}))["value"] == 5


def test_ref_resolves_feed_column_as_series():
    ctx = _ctx({"daily": [{"sha_1": 50}, {"sha_1": 52}]})
    result = eval_expr(_ref("sha_1", "daily"), ctx)
    assert result["value"] == [50, 52]


def test_comparison_auto_coerces_series_to_latest_value():
    ctx = _ctx({"daily": [{"sha_2": 45}, {"sha_2": 55}]})
    node = {"op": ">", "args": [_ref("sha_2", "daily"), {"op": "lit", "value": 50}]}
    assert eval_expr(node, ctx)["value"] is True


def test_crossed_below():
    # sha_2 was above sha_1, now below -> crossed down
    ctx = _ctx({"daily": [
        {"sha_1": 50, "sha_2": 55},
        {"sha_1": 50, "sha_2": 45},
    ]})
    node = {"op": "crossed_below", "args": [_ref("sha_2", "daily"), _ref("sha_1", "daily")]}
    assert eval_expr(node, ctx)["value"] is True


def test_crossed_below_false_when_no_prior_crossover():
    ctx = _ctx({"daily": [
        {"sha_1": 50, "sha_2": 40},
        {"sha_1": 50, "sha_2": 45},
    ]})
    node = {"op": "crossed_below", "args": [_ref("sha_2", "daily"), _ref("sha_1", "daily")]}
    assert eval_expr(node, ctx)["value"] is False


def test_falling():
    ctx = _ctx({"daily": [{"sha_2": 55}, {"sha_2": 45}]})
    node = {"op": "falling", "args": [_ref("sha_2", "daily")]}
    assert eval_expr(node, ctx)["value"] is True


def test_rising_needs_at_least_two_points():
    ctx = _ctx({"daily": [{"sha_2": 55}]})
    node = {"op": "rising", "args": [_ref("sha_2", "daily")]}
    assert eval_expr(node, ctx)["value"] is False


def test_and_or_not():
    true_node = {"op": "lit", "value": True}
    false_node = {"op": "lit", "value": False}
    assert eval_expr({"op": "and", "args": [true_node, true_node]}, _ctx({}))["value"] is True
    assert eval_expr({"op": "and", "args": [true_node, false_node]}, _ctx({}))["value"] is False
    assert eval_expr({"op": "or", "args": [false_node, true_node]}, _ctx({}))["value"] is True
    assert eval_expr({"op": "not", "args": [false_node]}, _ctx({}))["value"] is True


def test_if_only_evaluates_the_taken_branch():
    calls = []

    def _tracking_native(ctx, node):
        calls.append(node["plugin"])
        return node["plugin"] == "then_branch"

    node = {
        "op": "if",
        "args": [
            {"op": "lit", "value": True},
            {"op": "native", "plugin": "then_branch", "reads": [], "type": "Boolean"},
            {"op": "native", "plugin": "else_branch", "reads": [], "type": "Boolean"},
        ],
    }
    ctx = _ctx({})
    ctx["native_plugins"] = {
        "then_branch": {"eval": _tracking_native},
        "else_branch": {"eval": _tracking_native},
    }
    result = eval_expr(node, ctx)
    assert result["value"] is True
    assert calls == ["then_branch"]


def test_highest_lowest_ema():
    ctx = _ctx({"spot": [{"close": v} for v in [10, 12, 9, 15, 11]]})
    highest = {"op": "highest", "args": [_ref("close", "spot")], "length": 3}
    lowest = {"op": "lowest", "args": [_ref("close", "spot")], "length": 3}
    assert eval_expr(highest, ctx)["value"] == 15
    assert eval_expr(lowest, ctx)["value"] == 9

    ema = {"op": "ema", "args": [_ref("close", "spot")], "length": 3}
    ema_series = eval_expr(ema, ctx)["value"]
    assert isinstance(ema_series, list) and len(ema_series) == 5


def test_within_time_window():
    ctx = _ctx({}, clock_time=datetime.time(9, 25))
    node = {"op": "within_time_window", "args": [{"op": "lit", "value": "09:20"}, {"op": "lit", "value": "14:30"}]}
    assert eval_expr(node, ctx)["value"] is True

    ctx_outside = _ctx({}, clock_time=datetime.time(15, 0))
    assert eval_expr(node, ctx_outside)["value"] is False


def test_confirmation_agrees_reads_last_closed_row_of_second_feed():
    ctx = _ctx({"hourly": [{"sha_1": 50, "sha_2": 60}, {"sha_1": 50, "sha_2": 45}]})
    node = {"op": "confirmation_agrees", "feed": "hourly", "column": "sha_2",
            "operator": "<", "compare_to": "sha_1"}
    assert eval_expr(node, ctx)["value"] is True


def test_confirmation_agrees_false_when_feed_empty():
    ctx = _ctx({"hourly": []})
    node = {"op": "confirmation_agrees", "feed": "hourly", "column": "sha_2",
            "operator": "<", "compare_to": "sha_1"}
    assert eval_expr(node, ctx)["value"] is False


def test_native_node_dispatches_to_ctx_registry():
    ctx = _ctx({})
    ctx["native_plugins"] = {"ml_score": {"eval": lambda c, n: 0.87}}
    node = {"op": "native", "plugin": "ml_score", "reads": ["daily"], "type": NUMBER, "args": []}
    assert eval_expr(node, ctx)["value"] == 0.87


def test_is_compatible_number_accepts_series_for_auto_coercion():
    assert is_compatible(SERIES, NUMBER) is True
    assert is_compatible(NUMBER, SERIES) is False
    assert is_compatible(BOOLEAN, NUMBER) is False


def test_every_op_has_a_spec_with_a_label():
    for name, entry in EXPRESSION_OPS.items():
        assert "label" in entry["spec"], f"{name} missing a catalog label"
