import pytest

from trigerr.framework.instrument import (resolve_leg_to_tradable_symbol, resolve_exchange_for_leg,
                                          expiry_tag)


class FakeRedis:
    """ The expiry map the collector writes when a lane starts. """

    def __init__(self, hashes=None):
        self.hashes = hashes if hashes is not None else {
            "NIFTY_options_expiries": {"current": "2026-08-27", "near": "2026-09-24"},
            "NIFTY_futures_expiries": {"current": "2026-08-27"},
        }

    def hget(self, key, field):
        return (self.hashes.get(key) or {}).get(field)


def _ctx(spot_price=23456, strike_difference=50, lot_size=25, redis_cursor=None):
    return {"underlying": "NIFTY", "lot_size": lot_size, "spot_price": spot_price,
            "rdb_cursor": redis_cursor if redis_cursor is not None else FakeRedis(),
            "symbols_dict": {"strike_difference": strike_difference, "lot_size": lot_size}}


def test_spot_selector():
    leg = resolve_leg_to_tradable_symbol(_ctx(), {"side": "BUY", "instrument": {"selector": "spot"}})
    assert leg["exit_symbol"] == "NIFTY"
    assert leg["position_type"] == "LONG"
    assert leg["transaction_type"] == "BUY"
    assert leg["lot_size"] == 1


def test_futures_selector():
    leg = resolve_leg_to_tradable_symbol(_ctx(), {"side": "SELL", "instrument": {"selector": "futures"}})
    assert leg["exit_symbol"] == "NIFTY_FUTURES_2026-08-27"
    assert leg["position_type"] == "SHORT"
    assert leg["lot_size"] == 25


def test_atm_option_selector():
    leg = resolve_leg_to_tradable_symbol(
        _ctx(spot_price=23456), {"side": "BUY", "instrument": {"selector": "atm_option", "option_type": "PE"}})
    assert leg["strike_price"] == 23450
    assert leg["exit_symbol"] == "NIFTY_23450_PE_2026-08-27"
    assert leg["option_type"] == "PE"
    assert leg["leg_key"] == "PE"


def test_strike_offset_option_selector_otm_and_itm():
    ctx = _ctx(spot_price=23456)
    otm_ce = resolve_leg_to_tradable_symbol(
        ctx, {"side": "SELL", "instrument": {"selector": "strike_offset_option", "option_type": "CE",
                                             "direction": "otm", "offset": 100}})
    assert otm_ce["strike_price"] == 23550

    itm_ce = resolve_leg_to_tradable_symbol(
        ctx, {"side": "SELL", "instrument": {"selector": "strike_offset_option", "option_type": "CE",
                                             "direction": "itm", "offset": 100}})
    assert itm_ce["strike_price"] == 23350


def test_leg_key_defaults_to_option_type_or_exit_symbol():
    ctx = _ctx()
    option_leg = resolve_leg_to_tradable_symbol(
        ctx, {"side": "BUY", "instrument": {"selector": "atm_option", "option_type": "CE"}})
    assert option_leg["leg_key"] == "CE"

    spot_leg = resolve_leg_to_tradable_symbol(ctx, {"side": "BUY", "instrument": {"selector": "spot"}})
    assert spot_leg["leg_key"] == "NIFTY"


def test_explicit_leg_key_is_not_overridden():
    ctx = _ctx()
    leg = resolve_leg_to_tradable_symbol(
        ctx, {"leg_key": "short_call", "side": "SELL",
              "instrument": {"selector": "atm_option", "option_type": "CE"}})
    assert leg["leg_key"] == "short_call"


def test_resolve_exchange_for_leg_routes_derivatives_to_fo_segment():
    assert resolve_exchange_for_leg("XNSE", "spot") == "NSE"
    assert resolve_exchange_for_leg("XNSE", "atm_option") == "NFO"
    assert resolve_exchange_for_leg("XBSE", "futures") == "BFO"
    assert resolve_exchange_for_leg("OTHER", "atm_option") == "OTHER"


# --- absolute expiry resolution -------------------------------------------

def test_expiry_tag_reads_what_the_collector_published():
    assert expiry_tag(_ctx(), "options") == "2026-08-27"
    assert expiry_tag(_ctx(), "options", "near") == "2026-09-24"
    assert expiry_tag(_ctx(), "futures") == "2026-08-27"


def test_expiry_tag_decodes_bytes():
    """ redis-py returns bytes unless decode_responses is set, and the
    strategies' cursor does not set it. """
    redis = FakeRedis({"NIFTY_options_expiries": {"current": b"2026-08-27"}})
    assert expiry_tag(_ctx(redis_cursor=redis), "options") == "2026-08-27"


def test_missing_expiry_map_raises_rather_than_guessing():
    """ Falling back to a relative name resolves to whatever board that name
    points at -- right until the day it silently is not, and the strategy
    cannot tell the difference from the data. """
    with pytest.raises(LookupError, match="NIFTY_options_expiries"):
        expiry_tag(_ctx(redis_cursor=FakeRedis({})), "options", timeout_s=0)


def test_channel_carries_the_board_the_leg_is_actually_on():
    """ The whole point: a name that cannot mean a different contract tomorrow. """
    leg = resolve_leg_to_tradable_symbol(
        _ctx(), {"side": "BUY", "instrument": {"selector": "atm_option", "option_type": "CE"}})

    assert leg["exit_symbol"].endswith("_2026-08-27")
    assert "_near" not in leg["exit_symbol"], "relative words do not belong in a channel name"
