"""
A trade ends when an exit leaves nothing open, as well as when the exit carries one of the policy's last-exit names.

The lots of a position are split between the targets in whole numbers and what is left over goes to the first target, so with few
lots (one lot, or a big share at the first target) the first target sells the whole position and the exits that were to follow get
nothing. convert_to_trades used to end a trade only on a named last exit (order_exit_levels), so such a trade was never closed and
its record was lost (the strategies' `convert_to_trades(...)[-1]` raised IndexError). quantity_left is what check_open_orders reads
to say a position is closed, so an exit whose quantity_left is zero ends the trade too.

Offline: no Mongo, no Redis, no network.
"""
import datetime

from trigerr.orders import orders_utils

LEVELS = ["SL", "TSL", "LSL", "MARKETEXIT", "T2"]          # strat_crb's T1|T2: T1 is not a last exit


def entry_order(quantity, **extra):
    order = {
        "symbol": "NIFTY_22600_PE", "data_key": "UPSTOX:XNSE:NIFTY_22600_PE", "group_id": "r1:1",
        "trade_action": "ENTRY", "date": datetime.datetime(2026, 10, 22), "day": "Thursday",
        "order_timestamp": "2026-10-22 13:38:00", "trigger_price": 100.0, "quantity": quantity, "quantity_left": quantity,
        "lot_size": 65, "investment": 100000, "position_type": "LONG", "exchange": "NFO", "market": "IN", "order_type": "MARKET",
        "user_id": "507f1f77bcf86cd799439011", "strategy_id": "507f1f77bcf86cd799439012", "request_id": "507f1f77bcf86cd799439013",
    }
    order.update(extra)
    return order


def exit_order(exit_type, quantity, left, price, minute, **extra):
    order = {
        "symbol": "NIFTY_22600_PE", "trade_action": "EXIT", "exit_type": exit_type, "quantity": quantity, "quantity_left": left,
        "order_timestamp": f"2026-10-22 13:{minute}:00", "trigger_price": price, "position_type": "LONG", "order_type": "MARKET",
    }
    order.update(extra)
    return order


def convert(orders, levels=LEVELS):
    return orders_utils.convert_to_trades(orders_list=orders, market_type="options", order_exit_levels=levels, mode="vt", broker="zerodha")


def test_a_target_that_sells_the_whole_position_ends_the_trade():
    (trade,) = convert([entry_order(1), exit_order("T1", 1, 0, 110.0, 50)])
    assert (trade["exit_type"], trade["exit_price"], trade["exit_time"]) == ("T1", 110.0, "2026-10-22 13:50:00")
    assert trade["points"] == 10 and trade["pnl"] == 10 * 1 * 65
    assert trade["brokerage"] > 0 and trade["net_pnl"] > 0


def test_a_target_that_sells_part_of_the_position_does_not_end_it_and_the_last_exit_does_as_before():
    orders = [entry_order(44), exit_order("T1", 22, 22, 110.0, 50)]
    assert convert(orders) == []

    (trade,) = convert(orders + [exit_order("SL", 22, 0, 95.0, 55)])
    assert trade["exit_type"] == "T1|SL" and trade["exit_price"] == 95.0
    assert trade["points"] == 10 + -5 and trade["pnl"] == (22 * 10 - 22 * 5) * 65


def test_two_trades_in_one_list_each_end_where_they_ran_out():
    first = [entry_order(1), exit_order("T1", 1, 0, 110.0, 50)]
    second = [entry_order(44, order_timestamp="2026-10-22 14:00:00"), exit_order("SL", 44, 0, 95.0, 20, order_timestamp="2026-10-22 14:20:00")]
    trades = convert(first + second)
    assert [(trade["exit_type"], trade["quantity"]) for trade in trades] == [("T1", 1), ("SL", 44)]


def test_a_named_last_exit_still_ends_the_trade_whatever_it_says_is_left():
    (trade,) = convert([entry_order(44), exit_order("SL", 22, 22, 95.0, 50)])
    assert trade["exit_type"] == "SL"


def test_an_exit_that_does_not_say_what_is_left_is_judged_by_its_name_alone():
    orders = [entry_order(1), exit_order("T1", 1, 0, 110.0, 50)]
    del orders[1]["quantity_left"]
    assert convert(orders) == []
    assert len(convert(orders + [exit_order("SL", 0, 0, 95.0, 55)])) == 1


def test_a_part_fill_does_not_end_the_trade_and_the_fill_that_empties_it_does():
    """ The position manager records a fill that covers only part of an exit as <name>_PART, so the real name closes the trade. """
    part = exit_order("T2_PART", 10, 34, 108.0, 50)
    rest = exit_order("T2", 34, 0, 108.0, 51)
    assert convert([entry_order(44), part]) == []
    (trade,) = convert([entry_order(44), part, rest])
    assert trade["exit_type"] == "T2_PART|T2"


def test_a_list_closed_by_a_single_manual_level_still_ends_on_the_manual_exit():
    """ orders-api's exit_position converts with order_exit_levels=["MANUAL"] and takes the last trade: that must stay the manual one,
    with earlier trades of the day in the list. """
    earlier = [entry_order(44), exit_order("SL", 44, 0, 95.0, 10)]
    manual = [entry_order(44, order_timestamp="2026-10-22 14:00:00"), exit_order("MANUAL", 44, 0, 104.0, 30, order_timestamp="2026-10-22 14:30:00")]
    trades = convert(earlier + manual, levels=["MANUAL"])
    assert trades[-1]["exit_type"] == "MANUAL" and trades[-1]["exit_price"] == 104.0
