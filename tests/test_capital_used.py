"""
Every trade carries two amounts: `investment`, the capital set aside for it, and `capital_used`, what its entry really
put to work. `quantity` counts units for spot and futures and lots for everything else (the rule the P&L is priced
with), and an order carries the `leverage` it was sized with, so the used amount is the position value over it.

Offline: no Mongo, no Redis, no network.
"""
import datetime

import pytest

from trigerr.orders import orders_utils


def entry_order(**extra):
    order = {
        "symbol": "NIFTY_22600_PE", "data_key": "UPSTOX:XNSE:NIFTY_22600_PE", "group_id": "r1:1",
        "trade_action": "ENTRY", "date": datetime.datetime(2026, 10, 22), "day": "Thursday",
        "order_timestamp": "2026-10-22 13:38:00", "trigger_price": 136.9, "quantity": 11,
        "lot_size": 65, "investment": 100000, "position_type": "LONG", "exchange": "NFO",
        "market": "IN", "order_type": "MARKET", "quantity_left": 0,
        "user_id": "507f1f77bcf86cd799439011", "strategy_id": "507f1f77bcf86cd799439012",
        "request_id": "507f1f77bcf86cd799439013",
    }
    order.update(extra)
    return order


def exit_order(**extra):
    order = {
        "symbol": "NIFTY_22600_PE", "trade_action": "EXIT", "exit_type": "T1", "quantity_left": 0,
        "order_timestamp": "2026-10-22 13:50:00", "trigger_price": 150.0, "quantity": 11,
        "position_type": "LONG", "order_type": "MARKET",
    }
    order.update(extra)
    return order


def converted(market_type="options", entry=None, exit=None):
    trades = orders_utils.convert_to_trades(
        orders_list=[entry_order(**(entry or {})), exit_order(**(exit or {}))],
        market_type=market_type, order_exit_levels=["T1"], mode="vt", broker="zerodha")
    assert trades is not None and len(trades) == 1
    return trades[0]


def test_options_count_lots_times_lot_size():
    trade = converted()
    assert trade["capital_used"] == round(136.9 * 11 * 65, 2) == 97883.5


def test_the_capital_set_aside_is_kept_and_is_a_little_more_than_was_used():
    trade = converted()
    assert trade["investment"] == 100000
    assert trade["capital_used"] < trade["investment"]


def test_futures_and_spot_count_units_not_lots():
    futures = converted(market_type="futures", entry={"quantity": 3, "lot_size": 50, "trigger_price": 100}, exit={"quantity": 3})
    assert futures["capital_used"] == 300
    spot = converted(market_type="spot", entry={"quantity": 10, "lot_size": 1, "trigger_price": 250}, exit={"quantity": 10})
    assert spot["capital_used"] == 2500


def test_leverage_divides_the_position_value():
    trade = converted(entry={"quantity": 10, "lot_size": 25, "trigger_price": 100, "leverage": 5}, exit={"quantity": 10})
    assert trade["capital_used"] == 5000
    futures = converted(market_type="futures", entry={"quantity": 3, "trigger_price": 100, "leverage": 10}, exit={"quantity": 3})
    assert futures["capital_used"] == 30


@pytest.mark.parametrize("leverage", [None, 0, 1])
def test_no_leverage_counts_as_one(leverage):
    extra = {} if leverage is None else {"leverage": leverage}
    assert converted(entry=extra)["capital_used"] == 97883.5


def test_a_fractional_crypto_position_keeps_its_cents():
    order = entry_order(market="CRYPTO", quantity=0.5, trigger_price=60000.25, lot_size=1, leverage=10)
    assert orders_utils.capital_used(order, "futures") == 3000.01


def test_every_trade_of_a_run_carries_it():
    orders = [entry_order(group_id="r1:1"), exit_order(), entry_order(group_id="r1:2", trigger_price=140.0), exit_order(trigger_price=120.0)]
    trades = orders_utils.convert_to_trades(orders_list=orders, market_type="options", order_exit_levels=["T1"], mode="vt", broker="zerodha")
    assert [trade["capital_used"] for trade in trades] == [97883.5, round(140.0 * 11 * 65, 2)]


def test_leverage_changes_what_was_used_not_the_profit_or_the_charges():
    plain = converted()
    leveraged = converted(entry={"leverage": 5})
    assert leveraged["capital_used"] == plain["capital_used"] / 5
    for field in ("pnl", "net_pnl", "brokerage", "pnl_percent"):
        assert leveraged[field] == plain[field]
