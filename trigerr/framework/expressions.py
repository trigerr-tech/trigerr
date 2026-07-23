""" The canonical expression grammar: every strategy condition — an entry
signal, a named "variable"/intent, a confirmation check — is the same plain
node shape:

    {"op": <name>, "args": [<expr>, ...], ...op-specific keys, "type": <inferred>}

EXPRESSION_OPS is a registry of {name: {"eval", "arg_types", "return_type",
"spec"}} — the same function+spec pattern as the SDK's existing
apply_indicators. Adding an op costs one function + one registry entry; the
compiler and the UI catalog need no changes (the generality gate, Gate 0).

Type system (deliberately lean — see the plan's "no Price != Volume" call):
    Number   a scalar
    Boolean  a condition result
    Series   a column's values across a feed's history (a ref, or an
             indicator/transform of one)
    Time     a time-of-day value ("HH:MM" or datetime.time)
    Signal   reserved for the entry/exit leg-decision layer; no built-in op
             produces it yet.

Series-typed args are auto-coerced to their latest value wherever an op
expects a Number (see `_last`) — this is what lets `Close > EMA(20)` read
naturally without the author ever writing an explicit "current value" op. Ops
that need the raw history (crossed_above, rising, ema, ...) declare "Series"
and receive the list untouched. """

import datetime
import operator

import pandas as pd

NUMBER = "Number"
BOOLEAN = "Boolean"
SERIES = "Series"
TIME = "Time"
SIGNAL = "Signal"

_COMPATIBLE = {
    NUMBER: {NUMBER, SERIES},
    BOOLEAN: {BOOLEAN},
    SERIES: {SERIES},
    TIME: {TIME, NUMBER},
    "Any": {NUMBER, BOOLEAN, SERIES, TIME, SIGNAL},
}


def is_compatible(actual_type, expected_type):
    """ Whether a node of actual_type may feed into a slot expecting
    expected_type — the whole of the type-checking policy lives here. """
    return actual_type in _COMPATIBLE.get(expected_type, {expected_type})


def _last(value):
    """ Coerces a Series argument down to its most recent value; scalars and
    None pass through untouched. """
    if isinstance(value, list):
        return value[-1] if value else None
    return value


def _prev(value):
    """ The second-most-recent value of a Series; None if there isn't one. """
    if isinstance(value, list):
        return value[-2] if len(value) >= 2 else None
    return None


def eval_expr(node, ctx):
    """ Evaluates one AST node, annotating it with its "value" (the whole
    point of returning the node rather than a bare value: a false entry rule
    can then be rendered back with every subexpression's actual value —
    explainability falls out of this for free). Recurses via the op's own
    "eval" function, which calls back into eval_expr for its args. """
    op = node["op"]
    if op == "native":
        plugin = ctx["native_plugins"][node["plugin"]]
        value = plugin["eval"](ctx, node)
    else:
        value = EXPRESSION_OPS[op]["eval"](node, ctx)
    return {**node, "value": value}


# ---------------------------------------------------------------------------
# literal / reference / parameter
# ---------------------------------------------------------------------------

def _eval_lit(node, ctx):
    return node["value"]


def _eval_ref(node, ctx):
    """ A feed column (ctx={"feed": name}) resolves to that column's values
    across the feed's point-in-time-truncated rows, as a Series. A bare ref
    (no feed in its ctx) resolves against parameters. """
    feed_name = node.get("ctx", {}).get("feed")
    name = node["name"]
    if feed_name:
        return [row[name] for row in ctx["feeds"][feed_name]]
    return ctx["parameters"][name]


def _eval_param(node, ctx):
    return ctx["parameters"][node["name"]]


# ---------------------------------------------------------------------------
# arithmetic / comparison / logical / conditional
# ---------------------------------------------------------------------------

def _binary(fn):
    def _eval(node, ctx):
        a, b = (eval_expr(n, ctx)["value"] for n in node["args"])
        return fn(_last(a), _last(b))
    return _eval


def _eval_and(node, ctx):
    return all(eval_expr(n, ctx)["value"] for n in node["args"])


def _eval_or(node, ctx):
    return any(eval_expr(n, ctx)["value"] for n in node["args"])


def _eval_not(node, ctx):
    return not eval_expr(node["args"][0], ctx)["value"]


def _eval_if(node, ctx):
    cond, then_branch, else_branch = node["args"]
    branch = then_branch if eval_expr(cond, ctx)["value"] else else_branch
    return eval_expr(branch, ctx)["value"]


# ---------------------------------------------------------------------------
# series-aware ops
# ---------------------------------------------------------------------------

def _eval_crossed_above(node, ctx):
    fast, slow = (eval_expr(n, ctx)["value"] for n in node["args"])
    return _prev(fast) is not None and _prev(fast) <= _prev(slow) and _last(fast) > _last(slow)


def _eval_crossed_below(node, ctx):
    fast, slow = (eval_expr(n, ctx)["value"] for n in node["args"])
    return _prev(fast) is not None and _prev(fast) >= _prev(slow) and _last(fast) < _last(slow)


def _eval_rising(node, ctx):
    series = eval_expr(node["args"][0], ctx)["value"]
    return _prev(series) is not None and _last(series) > _prev(series)


def _eval_falling(node, ctx):
    series = eval_expr(node["args"][0], ctx)["value"]
    return _prev(series) is not None and _last(series) < _prev(series)


def _eval_highest(node, ctx):
    series = eval_expr(node["args"][0], ctx)["value"]
    return max(series[-node["length"]:])


def _eval_lowest(node, ctx):
    series = eval_expr(node["args"][0], ctx)["value"]
    return min(series[-node["length"]:])


def _eval_ema(node, ctx):
    series = eval_expr(node["args"][0], ctx)["value"]
    return pd.Series(series).ewm(span=node["length"], adjust=False).mean().tolist()


# ---------------------------------------------------------------------------
# time / cross-feed confirmation
# ---------------------------------------------------------------------------

def _parse_time(value):
    return datetime.datetime.strptime(value, "%H:%M").time() if isinstance(value, str) else value


def _eval_within_time_window(node, ctx):
    start = _parse_time(eval_expr(node["args"][0], ctx)["value"])
    end = _parse_time(eval_expr(node["args"][1], ctx)["value"])
    return start <= ctx["clock_time"] <= end


_COMPARE_OPERATORS = {"<": operator.lt, ">": operator.gt, "<=": operator.le,
                      ">=": operator.ge, "==": operator.eq, "!=": operator.ne}


def _eval_confirmation_agrees(node, ctx):
    """ The confirm_entry_condition pattern (7 of 15 backtest strategies): reads
    the last CLOSED row of a second feed and compares one column against
    another column or a literal. Point-in-time-safe because ctx["feeds"] is
    already truncated to the evaluation moment by the caller. """
    rows = ctx["feeds"][node["feed"]]
    if not rows:
        return False
    current = rows[-1][node["column"]]
    compare_to = node["compare_to"]
    other = rows[-1][compare_to] if isinstance(compare_to, str) and compare_to in rows[-1] else compare_to
    return _COMPARE_OPERATORS[node["operator"]](current, other)


EXPRESSION_OPS = {
    "lit":   {"eval": _eval_lit,   "arg_types": [], "return_type": "Any",
              "spec": {"label": "Literal value"}},
    "ref":   {"eval": _eval_ref,   "arg_types": [], "return_type": SERIES,
              "spec": {"label": "Feed column or parameter"}},
    "param": {"eval": _eval_param, "arg_types": [], "return_type": NUMBER,
              "spec": {"label": "Parameter value ($name sugar)"}},

    "+": {"eval": _binary(operator.add), "arg_types": [NUMBER, NUMBER], "return_type": NUMBER,
          "spec": {"label": "Add"}},
    "-": {"eval": _binary(operator.sub), "arg_types": [NUMBER, NUMBER], "return_type": NUMBER,
          "spec": {"label": "Subtract"}},
    "*": {"eval": _binary(operator.mul), "arg_types": [NUMBER, NUMBER], "return_type": NUMBER,
          "spec": {"label": "Multiply"}},
    "/": {"eval": _binary(operator.truediv), "arg_types": [NUMBER, NUMBER], "return_type": NUMBER,
          "spec": {"label": "Divide"}},

    ">":  {"eval": _binary(operator.gt), "arg_types": [NUMBER, NUMBER], "return_type": BOOLEAN,
           "spec": {"label": "Greater than"}},
    "<":  {"eval": _binary(operator.lt), "arg_types": [NUMBER, NUMBER], "return_type": BOOLEAN,
           "spec": {"label": "Less than"}},
    ">=": {"eval": _binary(operator.ge), "arg_types": [NUMBER, NUMBER], "return_type": BOOLEAN,
           "spec": {"label": "Greater than or equal"}},
    "<=": {"eval": _binary(operator.le), "arg_types": [NUMBER, NUMBER], "return_type": BOOLEAN,
           "spec": {"label": "Less than or equal"}},
    "==": {"eval": _binary(operator.eq), "arg_types": [NUMBER, NUMBER], "return_type": BOOLEAN,
           "spec": {"label": "Equal"}},
    "!=": {"eval": _binary(operator.ne), "arg_types": [NUMBER, NUMBER], "return_type": BOOLEAN,
           "spec": {"label": "Not equal"}},

    "and": {"eval": _eval_and, "arg_types": [BOOLEAN], "variadic": True, "return_type": BOOLEAN,
            "spec": {"label": "All of"}},
    "or":  {"eval": _eval_or,  "arg_types": [BOOLEAN], "variadic": True, "return_type": BOOLEAN,
            "spec": {"label": "Any of"}},
    "not": {"eval": _eval_not, "arg_types": [BOOLEAN], "return_type": BOOLEAN,
            "spec": {"label": "Not"}},
    "if":  {"eval": _eval_if,  "arg_types": [BOOLEAN, "Any", "Any"], "return_type": "Any",
            "spec": {"label": "If / then / else"}},

    "crossed_above": {"eval": _eval_crossed_above, "arg_types": [SERIES, SERIES], "return_type": BOOLEAN,
                       "spec": {"label": "Crossed above"}},
    "crossed_below": {"eval": _eval_crossed_below, "arg_types": [SERIES, SERIES], "return_type": BOOLEAN,
                       "spec": {"label": "Crossed below"}},
    "rising":  {"eval": _eval_rising,  "arg_types": [SERIES], "return_type": BOOLEAN,
                "spec": {"label": "Rising"}},
    "falling": {"eval": _eval_falling, "arg_types": [SERIES], "return_type": BOOLEAN,
                "spec": {"label": "Falling"}},
    "highest": {"eval": _eval_highest, "arg_types": [SERIES], "return_type": NUMBER,
                "spec": {"label": "Highest over N bars", "params": ["length"]}},
    "lowest":  {"eval": _eval_lowest,  "arg_types": [SERIES], "return_type": NUMBER,
                "spec": {"label": "Lowest over N bars", "params": ["length"]}},
    "ema":     {"eval": _eval_ema,     "arg_types": [SERIES], "return_type": SERIES,
                "spec": {"label": "Exponential moving average", "params": ["length"]}},

    "within_time_window": {"eval": _eval_within_time_window, "arg_types": [TIME, TIME], "return_type": BOOLEAN,
                            "spec": {"label": "Within time window"}},
    "confirmation_agrees": {"eval": _eval_confirmation_agrees, "arg_types": [], "return_type": BOOLEAN,
                             "spec": {"label": "Confirmation feed agrees",
                                      "params": ["feed", "column", "operator", "compare_to"]}},
}
