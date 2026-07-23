from trigerr.framework.catalog import build_block_catalog
from trigerr.framework.expressions import EXPRESSION_OPS
from trigerr.framework.exit_engine import EXIT_CONDITIONS
from trigerr.framework.instrument import INSTRUMENT_SELECTORS
from trigerr.framework.position_sizing import POSITION_SIZERS


def test_catalog_has_every_category():
    catalog = build_block_catalog()
    assert set(catalog) == {"expressions", "exit_conditions", "instrument_selectors", "position_sizers",
                            "data_feed_kinds", "candle_transforms"}


def test_every_catalog_entry_has_a_label():
    catalog = build_block_catalog()
    for category, entries in catalog.items():
        for name, spec in entries.items():
            assert spec.get("label"), f"{category}.{name} has no catalog label"


def test_catalog_entry_count_matches_registry_count():
    catalog = build_block_catalog()
    assert len(catalog["expressions"]) == len(EXPRESSION_OPS)
    assert len(catalog["exit_conditions"]) == len(EXIT_CONDITIONS)
    assert len(catalog["instrument_selectors"]) == len(INSTRUMENT_SELECTORS)
    assert len(catalog["position_sizers"]) == len(POSITION_SIZERS)


def test_generality_gate_new_op_costs_one_function_one_spec_zero_catalog_edits():
    """ Gate 0: adding a throwaway feed-kind-shaped op (standing in for a new
    data kind, e.g. "ticks") must show up in the catalog with no change to
    catalog.py or the compiler — one function + one registry entry only. """
    def _eval_tick_count(node, ctx):
        return len(ctx["feeds"][node["feed"]])

    EXPRESSION_OPS["tick_count"] = {
        "eval": _eval_tick_count, "arg_types": [], "return_type": "Number",
        "spec": {"label": "Tick count", "params": ["feed"]},
    }
    try:
        catalog = build_block_catalog()
        assert "tick_count" in catalog["expressions"]
        assert catalog["expressions"]["tick_count"]["label"] == "Tick count"
    finally:
        del EXPRESSION_OPS["tick_count"]


def test_generality_gate_new_exit_condition_and_selector_appear_automatically():
    def _check_stub(leg, ctx, trigger):
        return False

    def _resolve_stub(ctx, leg):
        leg["exit_symbol"] = "STUB"

    EXIT_CONDITIONS["stub_condition"] = _check_stub
    INSTRUMENT_SELECTORS["stub_selector"] = {"resolve": _resolve_stub, "spec": {"label": "Stub selector"}}
    try:
        catalog = build_block_catalog()
        assert "stub_condition" in catalog["exit_conditions"]
        assert "stub_selector" in catalog["instrument_selectors"]
        assert catalog["instrument_selectors"]["stub_selector"]["label"] == "Stub selector"
    finally:
        del EXIT_CONDITIONS["stub_condition"]
        del INSTRUMENT_SELECTORS["stub_selector"]
