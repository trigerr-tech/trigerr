""" Saving a live order or trade: a few tries, and an answer that says where the record really is. """
import datetime
from unittest.mock import patch

import pytest
from pymongo.errors import AutoReconnect, DuplicateKeyError

from trigerr.orders import live, orders_utils
from test_orders_schema import FakeDB, FakeRedis


class FlakyCollection:
    """ insert_one fails `failures` times, then saves. `lands` True: a failed try did reach the database. """
    def __init__(self, failures, lands=False):
        self.failures, self.lands, self.docs = failures, lands, []

    def insert_one(self, doc):
        doc.setdefault("_id", "id0")
        if any(saved["_id"] == doc["_id"] for saved in self.docs):
            raise DuplicateKeyError("duplicate")
        if self.failures:
            self.failures -= 1
            if self.lands:
                self.docs.append(dict(doc))
            raise AutoReconnect("connection lost")
        self.docs.append(dict(doc))
        return type("Result", (), {"inserted_id": doc["_id"]})()


class FlakyRedis(FakeRedis):
    """ rpush fails `failures` times, then works. `lands` True: a failed try did reach Redis. """
    def __init__(self, failures, lands=False):
        super().__init__()
        self.failures, self.lands = failures, lands

    def rpush(self, key, value):
        if self.failures:
            self.failures -= 1
            if self.lands:
                super().rpush(key, value)
            raise ConnectionError("socket closed")
        return super().rpush(key, value)


@pytest.fixture(autouse=True)
def quiet():
    with patch("trigerr.orders.orders_utils.time.sleep"), patch("trigerr.orders.live.send_order_alert"):
        yield


def save_order(db, redis_cursor):
    return live.save_lt_order(app_db_cursor=db, redis_cursor=redis_cursor, orders_list=[], symbol="NIFTY_23450_CE", quantity=2,
                              user_id="u1", strategy_id="s1", request_id="r1", exchange="NFO", order_id="OID1",
                              exchange_timestamp=datetime.datetime(2026, 1, 1, 9, 20))


def db_with(collection):
    db = FakeDB()
    db.cols["lt_orders"] = db.cols["lt_trades"] = collection
    return db


def test_a_save_that_fails_twice_then_works_is_a_success():
    collection, redis_cursor = FlakyCollection(failures=2), FlakyRedis(failures=2)
    status, orders = save_order(db_with(collection), redis_cursor)
    assert status == "success" and len(collection.docs) == 1 and len(orders) == 1


@pytest.mark.parametrize("failures", [1, 2])
def test_a_try_that_did_land_is_not_saved_twice(failures):
    collection, redis_cursor = FlakyCollection(failures, lands=True), FlakyRedis(failures, lands=True)
    status, orders = save_order(db_with(collection), redis_cursor)
    assert status == "success" and len(collection.docs) == 1 and len(orders) == 1


def test_mongo_down_and_redis_up_is_db_failed_and_the_order_is_in_the_list():
    status, orders = save_order(db_with(FlakyCollection(failures=99)), FakeRedis())
    assert status == "db_failed"
    assert len(orders) == 1 and orders[0]["order_id"] == "OID1" and "db_order_id" not in orders[0]


def test_redis_down_is_failed_whatever_mongo_did():
    collection = FlakyCollection(failures=0)
    status, orders = save_order(db_with(collection), FlakyRedis(failures=99))
    assert status == "failed" and orders == [] and len(collection.docs) == 1


def test_a_failed_order_alert_does_not_fail_the_save():
    with patch("trigerr.orders.live.send_order_alert", side_effect=RuntimeError("alert service down")):
        status, orders = save_order(FakeDB(), FakeRedis())
    assert status == "success" and len(orders) == 1


def test_save_lt_trade_says_whether_mongo_took_it():
    trade = {"request_id": "r1", "user_id": "u1", "pnl": 10}
    assert live.save_lt_trade(FakeDB(), FakeRedis(), dict(trade)) is True
    redis_cursor = FakeRedis()
    assert live.save_lt_trade(db_with(FlakyCollection(failures=99)), redis_cursor, dict(trade)) is False
    assert len(redis_cursor.lists["r1_trades"]) == 1


def test_add_order_to_redis_answers():
    order = {"user_id": "u1", "symbol": "X"}
    assert orders_utils.add_order_to_redis(FakeRedis(), "r1", order, "vt") is True
    assert orders_utils.add_order_to_redis(FlakyRedis(failures=99), "r1", order, "vt") is False
