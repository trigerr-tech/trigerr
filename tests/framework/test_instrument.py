from trigerr.framework.instrument import resolve_leg_to_tradable_symbol, resolve_exchange_for_leg


def _ctx(spot_price=23456, strike_difference=50, lot_size=25):
    return {"underlying": "NIFTY", "lot_size": lot_size, "spot_price": spot_price,
            "symbols_dict": {"strike_difference": strike_difference, "lot_size": lot_size}}


def test_spot_selector():
    leg = resolve_leg_to_tradable_symbol(_ctx(), {"side": "BUY", "instrument": {"selector": "spot"}})
    assert leg["exit_symbol"] == "NIFTY"
    assert leg["position_type"] == "LONG"
    assert leg["transaction_type"] == "BUY"
    assert leg["lot_size"] == 1


def test_futures_selector():
    leg = resolve_leg_to_tradable_symbol(_ctx(), {"side": "SELL", "instrument": {"selector": "futures"}})
    assert leg["exit_symbol"] == "NIFTY_FUTURES"
    assert leg["position_type"] == "SHORT"
    assert leg["lot_size"] == 25


def test_atm_option_selector():
    leg = resolve_leg_to_tradable_symbol(
        _ctx(spot_price=23456), {"side": "BUY", "instrument": {"selector": "atm_option", "option_type": "PE"}})
    assert leg["strike_price"] == 23450
    assert leg["exit_symbol"] == "NIFTY_23450_PE"
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
