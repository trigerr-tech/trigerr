""" Turns a strategy's declared sizing block into a leg quantity.
POSITION_SIZERS is a registry of {name: {"calculate", "spec"}} — same
function+spec pattern as the other registries.

ctx["sizing"] carries the resolved sizing params for the current run (the
strategy's "sizing" block with any "$name" values already substituted by
compiler.resolve_parameter_references — see that module for why this happens
at runtime, not compile time). """


def _capital_with_leverage(ctx, leg, entry_price):
    """ Ported from the legacy _size_leg_vt formula: invested capital times
    leverage, divided by the position's notional per unit. Requests carry
    numeric-looking inputs as strings (legacy's own eval(str(...)) pattern);
    float() here is the same coercion, applied at the point of use. """
    sizing = ctx["sizing"]
    leverage = float(sizing.get("leverage", 1))
    return (ctx["investment"] * leverage) / (entry_price * leg["lot_size"])


def _fixed_quantity(ctx, leg, entry_price):
    return ctx["sizing"]["quantity"]


def _risk_per_trade(ctx, leg, entry_price):
    """ Sizes so a stop-loss hit loses exactly risk_percent of investment:
    quantity = (investment * risk_percent / 100) / (|entry - stop| * lot_size). """
    sizing = ctx["sizing"]
    sl_distance = abs(entry_price - leg["sl_price"])
    if sl_distance <= 0:
        return 0
    risk_amount = ctx["investment"] * sizing["risk_percent"] / 100
    return risk_amount / (sl_distance * leg["lot_size"])


def _margin_based(ctx, leg, entry_price):
    """ Ported from strat_strdl_eios: a multi-leg entry sizes off the spot
    price and a shared margin pool (2 legs), not the option premium. Floors to
    min_quantity — a straddle always wants both legs on, unlike the other
    sizers here, where a below-floor quantity means don't take the trade at
    all (enforced by execution_core._size_leg, not here). """
    sizing = ctx["sizing"]
    margin_percent = float(sizing["margin_percent"])
    leverage = float(sizing.get("leverage", 1))
    margin_per_lot = ctx["spot_price"] * leg["lot_size"] * margin_percent / 100
    quantity = (ctx["investment"] * leverage) / (2 * margin_per_lot)
    return max(quantity, float(ctx["parameters"].get("min_quantity", 1)))


POSITION_SIZERS = {
    "capital_with_leverage": {"calculate": _capital_with_leverage,
                               "spec": {"label": "Capital x leverage", "params": ["leverage"]}},
    "fixed_quantity":        {"calculate": _fixed_quantity,
                               "spec": {"label": "Fixed quantity", "params": ["quantity"]}},
    "risk_per_trade":        {"calculate": _risk_per_trade,
                               "spec": {"label": "Risk a fixed % per trade",
                                        "params": ["risk_percent"]}},
    "margin_based":          {"calculate": _margin_based,
                               "spec": {"label": "Margin-based (multi-leg, shared pool)",
                                        "params": ["margin_percent", "leverage"]}},
}


def calculate_leg_quantity(ctx, leg, entry_price):
    """ Dispatches to ctx["sizing"]["sizer"]; markets that only trade whole
    units (US/IN equities/options) round down, matching legacy _size_leg_vt. """
    sizer = ctx["sizing"]["sizer"]
    quantity = POSITION_SIZERS[sizer]["calculate"](ctx, leg, entry_price)
    if ctx["market"] in ("US", "IN"):
        quantity = int(quantity)
    return quantity
