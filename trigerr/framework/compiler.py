""" The compiler: a pipeline of pure functions over the canonical strategy
AST (plain nested dicts — no AST classes, no OOP compiler). Every stage is
`dict -> dict` except validate, which is `dict -> [error strings]`.

    normalize -> resolve -> infer_types -> infer_subscriptions -> validate -> lower

`compile_strategy(source)` runs the whole pipeline and returns
`(execution_plan, errors)` — `execution_plan` is None when `errors` is
non-empty. This is deliberately not exception-based: a UI's Save button calls
`validate()` (via `compile_strategy`) and needs a list of readable problems
back, not a stack trace. """

from trigerr.framework.expressions import EXPRESSION_OPS, is_compatible

_TOP_LEVEL_DEFAULTS = {
    "meta": {}, "parameters": {}, "feeds": {}, "clock": None,
    "variables": {}, "entry": {"when": None, "legs": []},
    "exit": {"rules": []}, "sizing": {}, "native_plugins": {},
}

_MODULE_ATTR_MAP = {
    "META": "meta", "PARAMETERS": "parameters", "FEEDS": "feeds", "CLOCK": "clock",
    "VARIABLES": "variables", "ENTRY": "entry", "EXIT": "exit",
    "POSITION_SIZING": "sizing", "NATIVE_PLUGINS": "native_plugins",
}

_PARAM_TYPE_MAP = {"int": "Number", "float": "Number", "bool": "Boolean"}


# ---------------------------------------------------------------------------
# Stage 1 — normalize
# ---------------------------------------------------------------------------

def _desugar_expr(node):
    """ Bare "$name" strings become param-ref nodes; bare scalars become
    literal nodes; dict nodes recurse into their args. Lets a hand-written
    strategy skip wrapping every literal and parameter in its own dict. """
    if isinstance(node, dict) and "op" in node:
        desugared = dict(node)
        if "args" in desugared:
            desugared["args"] = [_desugar_expr(a) for a in desugared["args"]]
        return desugared
    if isinstance(node, str) and node.startswith("$"):
        return {"op": "param", "name": node[1:]}
    return {"op": "lit", "value": node}


def normalize(source):
    """ Accepts a Python module (module-level META/PARAMETERS/FEEDS/... names)
    or a plain dict already shaped like the canonical AST. Returns a fresh
    canonical dict; never mutates the input. """
    if isinstance(source, dict):
        raw = source
    else:
        raw = {}
        for attr, key in _MODULE_ATTR_MAP.items():
            if hasattr(source, attr):
                raw[key] = getattr(source, attr)

    ast = {key: (raw.get(key, default.copy() if isinstance(default, dict) else default))
           for key, default in _TOP_LEVEL_DEFAULTS.items()}
    ast["variables"] = {name: _desugar_expr(expr) for name, expr in ast["variables"].items()}
    entry = dict(ast["entry"])
    if entry.get("when") is not None:
        entry["when"] = _desugar_expr(entry["when"])
    ast["entry"] = entry
    ast["_errors"] = []
    return ast


# ---------------------------------------------------------------------------
# Stage 2 — resolve: inline variables, order derived feeds, catch cycles
# ---------------------------------------------------------------------------

def _inline_variables(node, variables, stack, errors):
    if not (isinstance(node, dict) and "op" in node):
        return node
    if node["op"] == "ref" and not node.get("ctx", {}).get("feed"):
        name = node["name"]
        if name in variables:
            if name in stack:
                errors.append(f"cycle in variables: {' -> '.join(stack + [name])}")
                return node
            return _inline_variables(variables[name], variables, stack + [name], errors)
        return node
    if "args" in node:
        return {**node, "args": [_inline_variables(a, variables, stack, errors) for a in node["args"]]}
    return node


def topological_feed_order(feeds, errors=None):
    """ Topologically orders feeds by "derive" dependency; a feed with no
    "derive" key has no dependency. Cycles are reported into `errors` (if
    given), not raised. Public: also called at runtime by
    data_feeds.resolve_feeds to know what order to resolve derived feeds in,
    so compile-time cycle detection and runtime resolution order are always
    the same computation. """
    errors = errors if errors is not None else []
    order, visiting, visited = [], set(), set()

    def visit(name, stack):
        if name in visited:
            return
        if name in visiting:
            errors.append(f"cycle in feeds: {' -> '.join(stack + [name])}")
            return
        if name not in feeds:
            return
        visiting.add(name)
        base = feeds[name].get("derive")
        if base:
            visit(base, stack + [name])
        visiting.discard(name)
        visited.add(name)
        order.append(name)

    for feed_name in feeds:
        visit(feed_name, [])
    return order


def resolve(ast):
    errors = list(ast["_errors"])
    variables = ast["variables"]

    resolved_variables = {}
    for name, expr in variables.items():
        resolved_variables[name] = _inline_variables(expr, variables, [name], errors)

    entry = dict(ast["entry"])
    if entry.get("when") is not None:
        entry["when"] = _inline_variables(entry["when"], variables, [], errors)

    return {**ast, "variables": resolved_variables, "entry": entry,
            "_feed_order": topological_feed_order(ast["feeds"], errors), "_errors": errors}


# ---------------------------------------------------------------------------
# Stage 3 — infer_types
# ---------------------------------------------------------------------------

def _literal_type(value):
    if isinstance(value, bool):
        return "Boolean"
    if isinstance(value, (int, float)):
        return "Number"
    return "Time"


def _infer_node_type(node, ast, errors):
    op = node.get("op")
    if op == "lit":
        return {**node, "type": _literal_type(node["value"])}
    if op == "param":
        param_spec = ast["parameters"].get(node["name"], {})
        return {**node, "type": _PARAM_TYPE_MAP.get(param_spec.get("type"), "Number")}
    if op == "ref":
        feed_name = node.get("ctx", {}).get("feed")
        if feed_name:
            return {**node, "type": "Series"}
        if node["name"] in ast["parameters"]:
            param_type = _PARAM_TYPE_MAP.get(ast["parameters"][node["name"]].get("type"), "Number")
            return {**node, "type": param_type}
        errors.append(f"unknown reference: {node['name']}")
        return {**node, "type": None}
    if op == "native":
        return {**node, "type": node.get("type")}
    if op not in EXPRESSION_OPS:
        errors.append(f"unknown op: {op}")
        return {**node, "type": None}

    op_spec = EXPRESSION_OPS[op]
    typed_args = [_infer_node_type(a, ast, errors) for a in node.get("args", [])]
    expected_types = op_spec["arg_types"]
    for i, arg in enumerate(typed_args):
        expected = expected_types[0] if op_spec.get("variadic") else (
            expected_types[i] if i < len(expected_types) else "Any")
        if arg["type"] is not None and not is_compatible(arg["type"], expected):
            errors.append(f"{op}: argument {i} expects {expected}, got {arg['type']}")
    return_type = op_spec["return_type"]
    return {**node, "args": typed_args, "type": ("Any" if return_type == "Any" else return_type)}


def infer_types(ast):
    errors = list(ast["_errors"])
    variables = {name: _infer_node_type(expr, ast, errors) for name, expr in ast["variables"].items()}
    entry = dict(ast["entry"])
    if entry.get("when") is not None:
        entry["when"] = _infer_node_type(entry["when"], {**ast, "variables": ast["variables"]}, errors)
    return {**ast, "variables": variables, "entry": entry, "_errors": errors}


# ---------------------------------------------------------------------------
# Stage 4 — infer_subscriptions
# ---------------------------------------------------------------------------

def _collect_subscriptions(node, subscriptions):
    if not (isinstance(node, dict) and "op" in node):
        return
    if node["op"] == "ref":
        feed_name = node.get("ctx", {}).get("feed")
        if feed_name:
            subscriptions.add(feed_name)
    if node["op"] == "native":
        subscriptions.update(node.get("reads", []))
    for arg in node.get("args", []):
        _collect_subscriptions(arg, subscriptions)


def infer_subscriptions(ast):
    """ Walks every expression to compute the feed set a run actually needs —
    "the user never configures subscriptions manually." Returns the set (also
    threaded through the ast as "_subscriptions" for validate/lower). """
    subscriptions = set()
    if ast["clock"]:
        subscriptions.add(ast["clock"])
    for expr in ast["variables"].values():
        _collect_subscriptions(expr, subscriptions)
    if ast["entry"].get("when") is not None:
        _collect_subscriptions(ast["entry"]["when"], subscriptions)
    return subscriptions


# ---------------------------------------------------------------------------
# Stage 5 — validate
# ---------------------------------------------------------------------------

def _collect_native_nodes(node, out):
    if not (isinstance(node, dict) and "op" in node):
        return
    if node["op"] == "native":
        out.append(node)
    for arg in node.get("args", []):
        _collect_native_nodes(arg, out)


def _collect_offset_violations(node, errors):
    if not (isinstance(node, dict) and "op" in node):
        return
    if node["op"] == "ref":
        offset = node.get("ctx", {}).get("offset", 0)
        if offset and offset > 0:
            errors.append(f"lookahead: ref {node['name']} has a future offset ({offset})")
    for arg in node.get("args", []):
        _collect_offset_violations(arg, errors)


def validate(ast):
    """ Returns a list of human-readable problems; empty means the strategy
    is valid. This is what a UI's Save button calls. """
    errors = list(ast["_errors"])

    if ast["clock"] is None:
        errors.append("no clock feed declared")
    elif ast["clock"] not in ast["feeds"]:
        errors.append(f"clock feed '{ast['clock']}' is not declared in feeds")

    subscriptions = infer_subscriptions(ast)
    for feed_name in subscriptions:
        if feed_name not in ast["feeds"]:
            errors.append(f"referenced feed '{feed_name}' is not declared in feeds")

    leg_keys = [leg.get("leg_key") for leg in ast["entry"].get("legs", [])]
    for leg_key in set(leg_keys):
        if leg_keys.count(leg_key) > 1:
            errors.append(f"duplicate leg_key: {leg_key}")

    when = ast["entry"].get("when")
    if when is not None:
        _collect_offset_violations(when, errors)
        native_nodes = []
        _collect_native_nodes(when, native_nodes)
        for node in native_nodes:
            if node.get("plugin") not in ast["native_plugins"]:
                errors.append(f"native node references undeclared plugin: {node.get('plugin')}")
            for feed_name in node.get("reads", []):
                if feed_name not in ast["feeds"]:
                    errors.append(f"native plugin '{node.get('plugin')}' reads undeclared feed: {feed_name}")

    declared_leg_keys = set(leg_keys)
    if declared_leg_keys:
        # Only meaningful when ENTRY.legs is declared statically. A plugin
        # using the check_entry_condition escape hatch decides its legs at
        # runtime - there is nothing here to validate against, and treating
        # an empty declared set as "no leg is valid" would false-positive on
        # every one of its exit rules.
        for rule in ast["exit"].get("rules", []):
            target = rule.get("legs", "ALL")
            if target != "ALL" and not isinstance(target, list) and target not in declared_leg_keys:
                errors.append(f"exit rule targets undeclared leg: {target}")

    return errors


def is_lookahead_verified(ast, plugin=None):
    """ False whenever a run's lookahead-safety can't be structurally
    guaranteed: the AST contains a native node (an opaque escape hatch whose
    body the compiler cannot inspect), or the plugin defines
    prepare_strategy_data (the same escape hatch at the plugin-hook level).
    A bt report should carry this verbatim (Gate 3). """
    when = ast["entry"].get("when")
    native_nodes = []
    if when is not None:
        _collect_native_nodes(when, native_nodes)
    for expr in ast.get("variables", {}).values():
        _collect_native_nodes(expr, native_nodes)
    if native_nodes:
        return False
    if plugin is not None and getattr(plugin, "prepare_strategy_data", None):
        return False
    return True


# ---------------------------------------------------------------------------
# Stage 6 — lower
# ---------------------------------------------------------------------------

def lower(ast):
    """ Strips compiler bookkeeping (the "_"-prefixed keys) and returns the
    validated AST as the execution plan. No scheduling/optimization passes
    yet — those are additive insertions into this stage when a profiler asks
    for them, not part of the foundation. """
    return {k: v for k, v in ast.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Runtime utility — non-AST param substitution (feed specs, exit rules, sizing)
# ---------------------------------------------------------------------------

def resolve_parameter_references(block, parameter_values):
    """ Recursively replaces bare "$name" strings with parameter_values[name]
    inside a plain dict/list/scalar block — for the non-AST parts of a
    strategy (feed specs, exit rule dicts, sizing params) that aren't
    evaluated by eval_expr. parameter_values is the flat, resolved runtime
    dict (defaults overlaid by the request's actual inputs), not the
    parameter spec. """
    if isinstance(block, dict):
        return {k: resolve_parameter_references(v, parameter_values) for k, v in block.items()}
    if isinstance(block, list):
        return [resolve_parameter_references(v, parameter_values) for v in block]
    if isinstance(block, str) and block.startswith("$"):
        return parameter_values[block[1:]]
    return block


# ---------------------------------------------------------------------------
# Convenience: the whole pipeline
# ---------------------------------------------------------------------------

def compile_strategy(source):
    """ Runs the full pipeline. Returns (execution_plan, errors) — errors is
    empty on success and execution_plan is None on failure. Never raises for
    an invalid strategy; that's what the returned errors list is for. """
    ast = normalize(source)
    ast = resolve(ast)
    ast = infer_types(ast)
    ast["_subscriptions"] = infer_subscriptions(ast)
    errors = validate(ast)
    if errors:
        return None, errors
    return lower(ast), []
