""" Turns a leg's declared "instrument" block into a concrete tradable symbol.
INSTRUMENT_SELECTORS is a registry of {name: {"resolve", "spec"}} — the same
function+spec pattern as EXPRESSION_OPS and EXIT_CONDITIONS; adding a new
instrument selector (a delta-targeted option, a calendar spread leg, ...)
costs one function + one entry, no dispatcher change.

A leg intent looks like:
    {"leg_key": "PE", "side": "BUY", "instrument": {"selector": "atm_option", "option_type": "PE"}}

"side" is always explicit ("BUY"/"SELL") — this is a deliberate simplification
over the legacy signal-derived direction ("UP"/"DOWN" -> CE/PE, long/short):
the new AST-authored leg always states its own side, so there's one source of
truth for direction instead of two paths that could disagree.

Only the selectors grounded in existing legacy logic are implemented: spot,
futures, atm_option, strike_offset_option. A delta-targeted selector needs an
options-greeks/IV data source nothing in this codebase provides yet — it is
deliberately not stubbed with fabricated behavior; add it when that data
source exists. """

from trigerr.utils import round_strike_price


def _resolve_spot(ctx, leg):
    leg["exit_symbol"] = ctx["underlying"]
    leg["lot_size"] = leg.get("lot_size", 1)
    leg["option_type"] = None
    leg["strike_price"] = None


def _resolve_futures(ctx, leg):
    leg["exit_symbol"] = f"{ctx['underlying'].replace(' ', '_')}_FUTURES"
    leg["lot_size"] = leg.get("lot_size", ctx["lot_size"])
    leg["option_type"] = None
    leg["strike_price"] = None


def _atm_strike(ctx, leg):
    spot_price = leg.get("spot_price", ctx["spot_price"])
    return int(round_strike_price(spot_price=spot_price, multiple=ctx["symbols_dict"]["strike_difference"]))


def _resolve_atm_option(ctx, leg):
    option_type = leg["instrument"]["option_type"]
    strike_price = _atm_strike(ctx, leg)
    leg["option_type"] = option_type
    leg["strike_price"] = strike_price
    leg["exit_symbol"] = f"{ctx['underlying'].replace(' ', '_')}_{strike_price}_{option_type}"
    leg["lot_size"] = leg.get("lot_size", int(str(ctx["symbols_dict"]["lot_size"])))


def _resolve_strike_offset_option(ctx, leg):
    option_type = leg["instrument"]["option_type"]
    direction = leg["instrument"].get("direction", "otm")
    offset = leg["instrument"].get("offset", 0)
    atm_strike = _atm_strike(ctx, leg)

    if direction == "otm":
        strike_price = atm_strike + offset if option_type == "CE" else atm_strike - offset
    else:  # itm
        strike_price = atm_strike - offset if option_type == "CE" else atm_strike + offset

    leg["option_type"] = option_type
    leg["strike_price"] = int(strike_price)
    leg["exit_symbol"] = f"{ctx['underlying'].replace(' ', '_')}_{int(strike_price)}_{option_type}"
    leg["lot_size"] = leg.get("lot_size", int(str(ctx["symbols_dict"]["lot_size"])))


INSTRUMENT_SELECTORS = {
    "spot":                 {"resolve": _resolve_spot,
                              "spec": {"label": "Underlying spot/cash", "params": []}},
    "futures":              {"resolve": _resolve_futures,
                              "spec": {"label": "Futures contract", "params": []}},
    "atm_option":           {"resolve": _resolve_atm_option,
                              "spec": {"label": "At-the-money option", "params": ["option_type"]}},
    "strike_offset_option": {"resolve": _resolve_strike_offset_option,
                              "spec": {"label": "Strike offset from ATM",
                                       "params": ["option_type", "direction", "offset"]}},
}


def resolve_leg_to_tradable_symbol(ctx, leg):
    """ Fills the leg dict with its concrete instrument details (exit_symbol,
    strike_price, option_type, lot_size, position_type, transaction_type),
    dispatching on leg["instrument"]["selector"]. """
    selector = leg["instrument"]["selector"]
    INSTRUMENT_SELECTORS[selector]["resolve"](ctx, leg)

    transaction_type = leg["side"]
    leg["transaction_type"] = transaction_type
    leg["position_type"] = "LONG" if transaction_type == "BUY" else "SHORT"
    leg.setdefault("leg_key", leg["option_type"] or leg["exit_symbol"])
    return leg


def resolve_exchange_for_leg(exchange, selector):
    """ NSE/BSE cash exchanges route F&O legs to their derivatives segment. """
    derivative = selector in ("futures", "atm_option", "strike_offset_option")
    if exchange == "XNSE":
        return "NFO" if derivative else "NSE"
    if exchange == "XBSE":
        return "BFO" if derivative else "BSE"
    return exchange
