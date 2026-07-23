from trigerr.framework.position_sizing import calculate_leg_quantity


def _ctx(sizing, market="IN", investment=100000):
    return {"sizing": sizing, "market": market, "investment": investment}


def test_capital_with_leverage_matches_legacy_formula():
    ctx = _ctx({"sizer": "capital_with_leverage", "leverage": 5}, investment=100000)
    leg = {"lot_size": 25}
    # legacy: (investment * leverage) / (entry_price * lot_size)
    quantity = calculate_leg_quantity(ctx, leg, entry_price=100)
    assert quantity == int((100000 * 5) / (100 * 25))


def test_fixed_quantity():
    ctx = _ctx({"sizer": "fixed_quantity", "quantity": 250})
    assert calculate_leg_quantity(ctx, {"lot_size": 25}, entry_price=100) == 250


def test_risk_per_trade_sizes_to_a_fixed_loss():
    ctx = _ctx({"sizer": "risk_per_trade", "risk_percent": 2}, investment=100000)
    leg = {"lot_size": 1, "sl_price": 90}
    quantity = calculate_leg_quantity(ctx, leg, entry_price=100)
    # risk_amount = 100000 * 2% = 2000; sl_distance = 10 -> quantity = 200
    assert quantity == 200


def test_risk_per_trade_zero_distance_is_zero_not_a_crash():
    ctx = _ctx({"sizer": "risk_per_trade", "risk_percent": 2})
    leg = {"lot_size": 1, "sl_price": 100}
    assert calculate_leg_quantity(ctx, leg, entry_price=100) == 0


def test_us_and_in_markets_round_down_others_do_not():
    ctx_in = _ctx({"sizer": "fixed_quantity", "quantity": 3.7}, market="IN")
    assert calculate_leg_quantity(ctx_in, {"lot_size": 1}, entry_price=1) == 3

    ctx_crypto = _ctx({"sizer": "fixed_quantity", "quantity": 3.7}, market="CRYPTO")
    assert calculate_leg_quantity(ctx_crypto, {"lot_size": 1}, entry_price=1) == 3.7
