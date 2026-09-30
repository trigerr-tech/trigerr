""" The two pieces a backtest stands on: the in-memory state cursor and the bt order document.

A backtest's order must be the vt order — same keys, same stringification, read back through the same
orders list — because one execution core serves vt, lt and bt. It may differ only where a backtest
must: stamped from the replayed candle, no database, no alert, no swallowed errors.
"""
import datetime
import types

import pytest

import trigerr.orders.virtual as virtual
import trigerr.utils as utils
from trigerr.framework.bt_state import memory_state_cursor
from trigerr.orders.backtest import place_bt_leg_order
from trigerr.orders.orders_utils import acquire_exit_mutex, fetch_orders_list, release_exit_mutex, renew_exit_mutex

CANDLE = {"symbol": "NIFTY_50", "close": 101.5, "timestamp": datetime.datetime(2025, 6, 2, 9, 31, 7, 500)}
ORDER = dict(quantity=5, quantity_left=5, position_type="LONG", transaction_type="BUY", trade_action="ENTRY",
             user_id="u1", strategy_id="s1", request_id="r1", market="IN", exchange="NSE", venue="XNSE",
             data_key="UPSTOX:XNSE:NIFTY_50", group_id="r1:2025-06-02:1", leg_key="SPOT", lot_size=1,
             params={"investment": 100000, "sl_price": 70.0})


# ---------------------------------------------------------------- memory_state_cursor

def test_memory_cursor_lists_behave_like_redis_lists():
    c = memory_state_cursor()
    assert c.rpush("k", "a") == 1 and c.rpush("k", "b", "c") == 3
    assert c.lrange("k", 0, -1) == ["a", "b", "c"] and c.lrange("k", 1, 1) == ["b"]
    assert c.llen("k") == 3 and c.llen("missing") == 0 and c.lrange("missing", 0, -1) == []


def test_memory_cursor_strings_and_set_nx():
    c = memory_state_cursor()
    assert c.set("m", "t1", nx=True, ex=120) is True
    assert c.set("m", "t2", nx=True, ex=120) is None          # already held
    assert c.get("m") == "t1" and c.get("nope") is None
    assert c.delete("m") == 1 and c.delete("m") == 0


def test_memory_cursor_publish_and_expire_are_harmless():
    c = memory_state_cursor()
    c.rpush("k", "x")
    assert c.publish("channel", "msg") == 0 and c.expire("k", 10) is True and c.expire("none", 10) is False


def test_exit_mutex_helpers_work_on_the_memory_cursor():
    c = memory_state_cursor()
    token = acquire_exit_mutex(c, "r1")
    assert token and acquire_exit_mutex(c, "r1", wait_s=0) is None     # mutually exclusive
    renew_exit_mutex(c, "r1", token)
    release_exit_mutex(c, "r1", "someone-elses-token")                 # must not free it
    assert acquire_exit_mutex(c, "r1", wait_s=0) is None
    release_exit_mutex(c, "r1", token)
    assert acquire_exit_mutex(c, "r1", wait_s=0)


# ---------------------------------------------------------------- place_bt_leg_order

def _vt_order_keys(monkeypatch):
    monkeypatch.setattr(virtual, "send_order_alert", lambda alert: None)
    db = {"vt_orders": types.SimpleNamespace(insert_one=lambda doc: types.SimpleNamespace(inserted_id="OID1"))}
    cursor = memory_state_cursor()
    orders = virtual.place_vt_order(app_db_cursor=db, redis_cursor=cursor, order_candle=CANDLE, **ORDER)
    return set(orders[-1])


def test_bt_order_has_exactly_the_vt_order_shape(monkeypatch):
    vt_keys = _vt_order_keys(monkeypatch)
    bt = place_bt_leg_order(redis_cursor=memory_state_cursor(), order_candle=CANDLE, **ORDER)[-1]
    assert vt_keys - {"db_order_id"} == set(bt)        # the only vt-only field is the database id


def test_bt_order_is_stamped_from_the_candle_and_keeps_its_fields():
    order = place_bt_leg_order(redis_cursor=memory_state_cursor(), order_candle=CANDLE, **ORDER)[-1]
    assert order["date"] == "2025-06-02 00:00:00"
    assert order["order_timestamp"] == "2025-06-02 09:31:07"      # microseconds dropped, like vt
    assert order["day"] == "Monday" and order["symbol"] == "NIFTY_50"
    assert order["trigger_price"] == 101.5                        # no explicit trigger -> the candle close
    assert order["sl_price"] == 70.0 and order["investment"] == 100000    # params folded in, like vt
    assert order["group_id"] == "r1:2025-06-02:1" and order["leg_key"] == "SPOT" and order["venue"] == "XNSE"


def test_bt_order_accumulates_on_the_request_orders_list():
    c = memory_state_cursor()
    place_bt_leg_order(redis_cursor=c, order_candle=CANDLE, **ORDER)
    second = place_bt_leg_order(redis_cursor=c, order_candle=CANDLE, **{**ORDER, "trade_action": "EXIT", "exit_type": "T1"})
    assert [o["trade_action"] for o in second] == ["ENTRY", "EXIT"]
    assert [o["trade_action"] for o in fetch_orders_list(c, "r1")] == ["ENTRY", "EXIT"]


def test_bt_order_sends_no_alert(monkeypatch):
    monkeypatch.setattr(utils, "send_order_alert", lambda *a, **k: (_ for _ in ()).throw(AssertionError("alert sent")))
    monkeypatch.setattr(virtual, "send_order_alert", lambda *a, **k: (_ for _ in ()).throw(AssertionError("alert sent")))
    place_bt_leg_order(redis_cursor=memory_state_cursor(), order_candle=CANDLE, **ORDER)


def test_bt_order_rejects_a_candle_without_a_datetime_timestamp():
    with pytest.raises(TypeError, match="datetime"):
        place_bt_leg_order(redis_cursor=memory_state_cursor(), order_candle={**CANDLE, "timestamp": "2025-06-02 09:31"},
                           **ORDER)


def test_bt_order_raises_when_nothing_was_stored():
    broken = types.SimpleNamespace(rpush=lambda *a: 0, expire=lambda *a: 0, publish=lambda *a: 0,
                                   lrange=lambda *a: [], llen=lambda k: 0)
    with pytest.raises(RuntimeError, match="not stored"):
        place_bt_leg_order(redis_cursor=broken, order_candle=CANDLE, **ORDER)
