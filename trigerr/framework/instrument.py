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

import datetime
import time

from trigerr.utils import round_strike_price

# The collector writes the expiry map when a lane starts, so a strategy
# dispatched in the first seconds of the session can beat it there.
_EXPIRY_WAIT_S = 60


def expiry_tag(ctx, asset_class, expiry_type="current", timeout_s=None):
    """ Turn "current"/"near" into the date the collector is actually publishing.

    Derivative channels carry the contract's own expiry --
    NIFTY_50_24000_CE_2026-08-27 -- rather than a relative word, because "near"
    means a different contract after every rollover: a position held across one
    would otherwise see the same channel name start carrying something else.

    Waits rather than guessing. Falling back to a relative name would resolve to
    whatever board that name pointed at, which is right until the day it silently
    is not -- and a strategy cannot tell the difference from the data.
    """
    redis_cursor = ctx.get("rdb_cursor")
    if redis_cursor is None:
        raise KeyError("expiry_tag needs ctx['rdb_cursor'] to read the expiry map")

    # ctx may shorten the wait. Without this a context that never publishes the
    # map costs the full wait per leg, so the symptom is a hang rather than the
    # error that is actually waiting at the end of it -- which is exactly how it
    # presented the first time a test forgot to provide one.
    if timeout_s is None:
        timeout_s = ctx.get("expiry_timeout_s", _EXPIRY_WAIT_S)

    key = f"{ctx['underlying'].replace(' ', '_')}_{asset_class}_expiries"
    deadline = time.time() + timeout_s
    while True:
        tag = redis_cursor.hget(key, expiry_type)
        if tag is not None:
            return tag.decode() if isinstance(tag, bytes) else tag
        if time.time() >= deadline:
            raise LookupError(
                f"no {expiry_type!r} expiry published under {key!r} after {timeout_s}s. "
                f"The {asset_class} lane for this underlying is not running, or it is "
                f"not collecting this underlying.")
        time.sleep(0.5)


def _resolve_spot(ctx, leg):
    leg["exit_symbol"] = ctx["underlying"]
    leg["lot_size"] = leg.get("lot_size", 1)
    leg["option_type"] = None
    leg["strike_price"] = None


def _resolve_futures(ctx, leg):
    leg["exit_symbol"] = (f"{ctx['underlying'].replace(' ', '_')}_FUTURES"
                          f"_{expiry_tag(ctx, 'futures')}")
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
    leg["exit_symbol"] = (f"{ctx['underlying'].replace(' ', '_')}_{strike_price}_{option_type}"
                          f"_{expiry_tag(ctx, 'options')}")
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
    leg["exit_symbol"] = (f"{ctx['underlying'].replace(' ', '_')}_{int(strike_price)}_{option_type}"
                          f"_{expiry_tag(ctx, 'options')}")
    leg["lot_size"] = leg.get("lot_size", int(str(ctx["symbols_dict"]["lot_size"])))


def _resolve_atm_option_near_month(ctx, leg):
    """ Same as atm_option, but takes the next expiry board once past the 20th
    of the month (strat_sha_edol's own monthly-contract-rollover convention for
    DELIVERY/multi-day positions — a real, wall-clock-dependent quirk in the
    legacy file itself, not something a replayable feed drives, so this reads
    the wall clock too rather than inventing a backtestable substitute legacy
    doesn't have).

    This used to append "_near" to a name already built for the current board.
    Now it asks for the near board's own date, which is the same intent stated
    once instead of a suffix pasted onto the wrong answer. """
    if datetime.datetime.today().date().day < 20:
        _resolve_atm_option(ctx, leg)
        return

    option_type = leg["instrument"]["option_type"]
    strike_price = _atm_strike(ctx, leg)
    leg["option_type"] = option_type
    leg["strike_price"] = strike_price
    leg["exit_symbol"] = (f"{ctx['underlying'].replace(' ', '_')}_{strike_price}_{option_type}"
                          f"_{expiry_tag(ctx, 'options', 'near')}")
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
    "atm_option_near_month": {"resolve": _resolve_atm_option_near_month,
                              "spec": {"label": "At-the-money option (near-month past the 20th)",
                                       "params": ["option_type"]}},
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
    derivative = selector in ("futures", "atm_option", "strike_offset_option", "atm_option_near_month")
    if exchange == "XNSE":
        return "NFO" if derivative else "NSE"
    if exchange == "XBSE":
        return "BFO" if derivative else "BSE"
    return exchange
