""" Task #99: stress-tests compile_strategy()/validate() against adversarial
and malformed AST input - a UI Save button (or a raw JSON POST straight to an
API, once the strategy builder is public per task #102) can send anything.
compile_strategy's own docstring already promises "never raises... that's
what the returned errors list is for" - this file exists to actually verify
that promise rather than trust it.

Every case here was confirmed to raise an uncaught exception BEFORE the
fixes in this same task: ValueError/TypeError/AttributeError/KeyError/
RecursionError, depending on which stage the malformed shape reached first.
Each test now asserts compile_strategy degrades to a readable error instead
of crashing - most also assert the specific message, since a silent
swallow-and-return-no-errors would be its own (worse) bug. """
import pytest

from trigerr.framework.compiler import compile_strategy

MINIMAL_LEGS = [{"leg_key": "CE"}]


def _valid_when():
    return {"op": "lit", "value": True}


def test_empty_source_does_not_crash():
    plan, errors = compile_strategy({})
    assert plan is None
    assert "no clock feed declared" in errors


def test_none_source_does_not_crash():
    plan, errors = compile_strategy(None)
    assert plan is None
    assert "no clock feed declared" in errors


@pytest.mark.parametrize("key", ["meta", "parameters", "feeds", "variables", "entry", "exit",
                                "sizing", "native_plugins"])
def test_wrong_type_top_level_block_is_coerced_not_crashed(key):
    """ Every dict-shaped top-level block must survive being sent as some
    other JSON type entirely (a string, a list, null) - this is the single
    most likely real mistake in a hand-built or generated JSON payload. """
    for bad_value in ("garbage", None, ["a", "b"], 5):
        source = {"clock": "spot", "feeds": {"spot": {}},
                  "entry": {"when": _valid_when(), "legs": []}, key: bad_value}
        plan, errors = compile_strategy(source)
        assert plan is None
        assert any(f"'{key}'" in e and "must be an object" in e for e in errors), \
            f"key={key} value={bad_value!r} errors={errors}"


def test_entry_legs_as_non_list_is_reported_not_crashed():
    source = {"clock": "spot", "feeds": {"spot": {}},
              "entry": {"when": _valid_when(), "legs": "PE"}}
    plan, errors = compile_strategy(source)
    assert plan is None
    assert any("entry.legs must be a list" in e for e in errors)


@pytest.mark.parametrize("bad_leg", [None, "PE", 5, ["nested", "list"]])
def test_entry_legs_containing_non_object_items_is_reported_not_crashed(bad_leg):
    source = {"clock": "spot", "feeds": {"spot": {}},
              "entry": {"when": _valid_when(), "legs": [bad_leg]}}
    plan, errors = compile_strategy(source)
    assert plan is None
    assert any("non-object leg" in e for e in errors)


def test_expression_args_as_non_list_is_coerced_not_crashed():
    source = {"clock": "spot", "feeds": {"spot": {}},
              "entry": {"when": {"op": "and", "args": 5}, "legs": []}}
    plan, errors = compile_strategy(source)
    # coerced to zero args rather than crashing on `for a in 5`; "and" over
    # zero args is vacuously true so this compiles clean - the point is only
    # that it doesn't raise TypeError: 'int' object is not iterable.
    assert errors == []
    assert plan is not None


def test_ref_node_missing_name_is_reported_not_crashed():
    source = {"clock": "spot", "feeds": {"spot": {}},
              "entry": {"when": {"op": "ref"}, "legs": []}}
    plan, errors = compile_strategy(source)
    assert plan is None
    assert any("ref node missing required 'name'" in e for e in errors)


def test_param_node_missing_name_is_reported_not_crashed():
    source = {"clock": "spot", "feeds": {"spot": {}},
              "entry": {"when": {"op": "param"}, "legs": []}}
    plan, errors = compile_strategy(source)
    assert plan is None
    assert any("param node missing required 'name'" in e for e in errors)


def test_ref_node_with_unhashable_name_is_reported_not_crashed():
    """ Not just missing - a "name" that's some unhashable JSON type (a list
    or object) crashed the same "in ast['parameters']"/"in variables" dict
    membership checks a missing name did; found only by randomized fuzzing,
    past the ~20 hand-enumerated cases above. """
    source = {"clock": "spot", "feeds": {"spot": {}},
              "entry": {"when": {"op": "ref", "name": ["not", "a", "string"]}, "legs": []}}
    plan, errors = compile_strategy(source)
    assert plan is None
    assert any("ref node missing required 'name'" in e for e in errors)


def test_param_node_with_unhashable_name_is_reported_not_crashed():
    source = {"clock": "spot", "feeds": {"spot": {}},
              "entry": {"when": {"op": "param", "name": {"a": 1}}, "legs": []}}
    plan, errors = compile_strategy(source)
    assert plan is None
    assert any("param node missing required 'name'" in e for e in errors)


def test_variable_ref_with_unhashable_name_does_not_crash():
    """ Same class of bug, hit in resolve()'s _inline_variables instead of
    infer_types()'s _infer_node_type - a "ref" node inlining a variable by
    name does its own separate dict-membership check on the same field. """
    source = {"clock": "spot", "feeds": {"spot": {}}, "variables": {"x": {"op": "lit", "value": 1}},
              "entry": {"when": {"op": "ref", "name": ["not", "a", "string"]}, "legs": []}}
    plan, errors = compile_strategy(source)
    assert plan is None


def test_ctx_feed_as_unhashable_value_does_not_crash():
    """ ctx.feed is supposed to be a feed name (string); a dict/list there
    must not crash the set() a subscription gets added to. """
    source = {"clock": "spot", "feeds": {"spot": {}},
              "entry": {"when": {"op": "ref", "name": "x", "ctx": {"feed": {"nested": "object"}}},
                       "legs": []}}
    plan, errors = compile_strategy(source)
    assert plan is not None or errors  # must not raise either way


def test_lookahead_offset_as_non_numeric_does_not_crash():
    source = {"clock": "spot", "feeds": {"spot": {}},
              "entry": {"when": {"op": "ref", "name": "close",
                                "ctx": {"feed": "spot", "offset": "not_a_number"}}, "legs": []}}
    plan, errors = compile_strategy(source)
    assert plan is not None
    assert errors == []


def test_exit_rule_target_as_unhashable_value_does_not_crash():
    source = {"clock": "spot", "feeds": {"spot": {}},
              "entry": {"when": _valid_when(), "legs": MINIMAL_LEGS},
              "exit": {"rules": [{"condition": "stoploss_hit", "exit_type": "SL",
                                  "legs": {"not": "a valid target"}}]}}
    plan, errors = compile_strategy(source)
    assert plan is not None or errors  # must not raise either way


def test_clock_as_unhashable_value_is_reported_not_crashed():
    source = {"clock": ["not", "a", "string"], "feeds": {"spot": {}},
              "entry": {"when": _valid_when(), "legs": []}}
    plan, errors = compile_strategy(source)
    assert plan is None
    assert any("clock must be a feed name" in e for e in errors)


def test_feed_spec_as_non_object_does_not_crash():
    source = {"clock": "spot", "feeds": {"spot": "garbage", "m15": {"derive": "spot"}},
              "entry": {"when": _valid_when(), "legs": []}}
    plan, errors = compile_strategy(source)
    assert plan is not None or errors  # must not raise either way


def test_lit_node_missing_value_does_not_crash():
    source = {"clock": "spot", "feeds": {"spot": {}},
              "entry": {"when": {"op": "lit"}, "legs": []}}
    plan, errors = compile_strategy(source)
    assert errors == []
    assert plan is not None


def test_malformed_parameter_spec_does_not_crash():
    """ parameters["sha_length"] itself must be an object ({"type":...,
    "default":...}) - a spec that's some other JSON type entirely (a string
    a UI accidentally serialized the whole spec into) must not crash the
    $sha_length reference that reads it. """
    source = {"clock": "spot", "feeds": {"spot": {}},
              "parameters": {"sha_length": "not_an_object"},
              "entry": {"when": {"op": "ref", "name": "sha_length"}, "legs": []}}
    plan, errors = compile_strategy(source)
    assert plan is not None
    assert errors == []


@pytest.mark.parametrize("bad_rule", [None, "garbage", 5, ["nested"]])
def test_exit_rule_as_non_object_is_reported_not_crashed(bad_rule):
    source = {"clock": "spot", "feeds": {"spot": {}},
              "entry": {"when": _valid_when(), "legs": MINIMAL_LEGS},
              "exit": {"rules": [bad_rule]}}
    plan, errors = compile_strategy(source)
    assert plan is None
    assert any("exit rule is not an object" in e for e in errors)


def test_deeply_nested_expression_reports_error_instead_of_stack_overflow():
    """ A UI could never construct this (no one nests 3000 "not"s by hand),
    but nothing stops a raw JSON POST from doing it deliberately - a genuine
    DoS-shaped adversarial input against a compiler with no depth limit. """
    deep = {"op": "lit", "value": True}
    for _ in range(3000):
        deep = {"op": "not", "args": [deep]}
    source = {"clock": "spot", "feeds": {"spot": {}}, "entry": {"when": deep, "legs": []}}
    plan, errors = compile_strategy(source)
    assert plan is None
    assert any("too deeply nested" in e for e in errors)


def test_variable_value_as_bare_scalar_is_already_safely_desugared():
    """ Not a bug - documenting existing, correct behavior: a variable whose
    value is a bare scalar (not even wrapped in {"op": "lit", ...}) is
    desugared to a literal node during normalize, same as any other bare
    scalar in the tree. """
    source = {"clock": "spot", "feeds": {"spot": {}}, "variables": {"x": 5},
              "entry": {"when": _valid_when(), "legs": []}}
    plan, errors = compile_strategy(source)
    assert errors == []
    assert plan is not None


ADVERSARIAL_SOURCES = [
    {}, None, "garbage", 5, [], ["a", "b"], True,
    {"entry": "garbage"}, {"entry": None}, {"entry": 5}, {"entry": []},
    {"clock": "spot", "feeds": {"spot": {}}, "entry": {"when": _valid_when(), "legs": "PE"}},
    {"clock": "spot", "feeds": {"spot": {}}, "entry": {"when": _valid_when(), "legs": [None, "x", 5]}},
    {"clock": "spot", "feeds": ["spot"], "entry": {"when": _valid_when(), "legs": []}},
    {"clock": "spot", "feeds": {"spot": {}}, "parameters": ["x"],
     "entry": {"when": _valid_when(), "legs": []}},
    {"clock": 5, "feeds": {"spot": {}}, "entry": {"when": _valid_when(), "legs": []}},
    {"clock": ["not", "a", "string"], "feeds": {"spot": {}}, "entry": {"when": _valid_when(), "legs": []}},
    {"clock": "spot", "feeds": {"spot": {}},
     "entry": {"when": {"op": "and", "args": [{"op": "ref"}, {"op": "param"}, {"op": "lit"}]}, "legs": []}},
    {"clock": "spot", "feeds": {"spot": {}},
     "entry": {"when": {"op": "native", "plugin": None, "reads": None, "args": []}, "legs": []}},
]


@pytest.mark.parametrize("source", ADVERSARIAL_SOURCES, ids=range(len(ADVERSARIAL_SOURCES)))
def test_compile_strategy_never_raises_a_fuzz_sweep(source):
    """ Umbrella sweep, deliberately broader than the individually-named
    cases above: asserts only the contract compile_strategy's own docstring
    already claims (never raises), not any specific error content - catches
    future regressions even for shapes not individually enumerated. """
    plan, errors = compile_strategy(source)
    assert (plan is None) == bool(errors) or (plan is not None and errors == [])
