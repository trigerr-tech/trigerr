""" The order ledger must account for every lot, not the last entry per symbol.

`check_open_orders` folds an orders list into open positions keyed by SYMBOL, and each ENTRY order overwrites the
previous one's fields for that symbol (quantity, quantity_left, trigger_price, group_id ...). Two entries in the
same instrument — pyramiding, a grid, an adjustment that re-opens a strike, two overlapping structures — therefore
report only the last lot, and a restart rebuilds only that one. No running strategy does this today; the
families on the roadmap do.
"""
import pytest

from trigerr.orders.orders_utils import check_open_orders

SYMBOL = "NIFTY_50_24000_CE_2026-08-27"


def _entry(group, quantity, price, minute):
    return {"symbol": SYMBOL, "trade_action": "ENTRY", "quantity": quantity, "quantity_left": quantity,
            "trigger_price": price, "order_timestamp": f"2025-06-02 09:{minute:02d}:00", "position_type": "LONG",
            "group_id": group, "leg_key": "CE", "data_key": f"UPSTOX:XNSE:{SYMBOL}", "venue": "XNSE", "lot_size": 25}


def test_one_entry_is_one_open_position():
    open_positions = check_open_orders([_entry("r1:2025-06-02:1", 10, 100.0, 16)])
    assert {s: p["quantity_left"] for s, p in open_positions.items()} == {SYMBOL: 10}


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="S6: open positions are keyed by symbol and the second ENTRY overwrites the first, so a "
                          "second lot in the same instrument hides the first (15 open lots are reported as 5)")
def test_two_entries_in_the_same_instrument_are_both_open():
    orders = [_entry("r1:2025-06-02:1", 10, 100.0, 16), _entry("r1:2025-06-02:2", 5, 110.0, 30)]
    open_positions = check_open_orders(orders)
    assert sum(p["quantity_left"] for p in open_positions.values()) == 15
