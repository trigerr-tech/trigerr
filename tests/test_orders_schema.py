""" Task B1 (spec §8.1 order document, §8.2 multi-leg sequencing):
- vt/lt order documents carry symbol/venue/data_key/group_id/leg_key (+ broker/
  broker_symbol for lt) instead of tradingsymbol.
- orders_utils readers (check_open_orders, check_existing_order,
  convert_to_trades) work off the new `symbol` field.
- sequence() orders BUY before SELL, stably.

Offline: fake Mongo/Redis, no real network (send_order_alert is monkeypatched
out — it otherwise POSTs to orders_url).
"""
import datetime

from trigerr.orders import orders_utils, virtual, live


# ---------------------------------------------------------------------------
# Fakes for Mongo/Redis (no real network, no real datastore)
# ---------------------------------------------------------------------------

class FakeCollection:
    def __init__(self):
        self.docs = []

    def insert_one(self, doc):
        doc = dict(doc)
        doc["_id"] = f"id{len(self.docs)}"
        self.docs.append(doc)
        return type("Result", (), {"inserted_id": doc["_id"]})()


class FakeDB:
    def __init__(self):
        self.cols = {}

    def __getitem__(self, name):
        return self.cols.setdefault(name, FakeCollection())


class FakeRedis:
    def __init__(self):
        self.lists = {}

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)
        return len(self.lists[key])

    def expire(self, key, ttl):
        pass

    def publish(self, channel, message):
        pass

    def lrange(self, key, start, end):
        values = self.lists.get(key, [])
        return values[start:] if end == -1 else values[start:end + 1]


def _order_candle(symbol="NIFTY_23450_CE", close=100):
    return {"symbol": symbol, "close": close, "timestamp": datetime.datetime(2026, 1, 1, 9, 20)}


# ---------------------------------------------------------------------------
# 1. Order document — vt and lt
# ---------------------------------------------------------------------------

def test_place_vt_order_document_has_new_schema_no_tradingsymbol(monkeypatch):
    monkeypatch.setattr(virtual, "send_order_alert", lambda *a, **k: None)
    db, redis_cursor = FakeDB(), FakeRedis()

    orders_list = virtual.place_vt_order(
        app_db_cursor=db, redis_cursor=redis_cursor, order_candle=_order_candle(), quantity=25,
        user_id="u1", strategy_id="s1", request_id="r1", exchange="NFO",
        data_key="UPSTOX:XNSE:NIFTY_23450_CE", venue="XNSE", group_id="r1:1", leg_key="CE")

    order = orders_list[-1]
    assert "tradingsymbol" not in order
    assert order["symbol"] == "NIFTY_23450_CE"
    assert order["venue"] == "XNSE"
    assert order["data_key"] == "UPSTOX:XNSE:NIFTY_23450_CE"
    assert order["group_id"] == "r1:1"
    assert order["leg_key"] == "CE"
    assert order["exchange"] == "NFO"  # kept for brokerage/OMS until Track B2


def test_place_vt_order_new_fields_default_none(monkeypatch):
    """ The new keyword params are optional and don't disturb positional/
    keyword callers that don't know about them yet. """
    monkeypatch.setattr(virtual, "send_order_alert", lambda *a, **k: None)
    db, redis_cursor = FakeDB(), FakeRedis()

    orders_list = virtual.place_vt_order(
        app_db_cursor=db, redis_cursor=redis_cursor, order_candle=_order_candle(), quantity=25,
        user_id="u1", strategy_id="s1", request_id="r1")

    # Round-tripped through the (fake) Redis list, so None comes back as the
    # string "None" like every other unset field here -- not a schema detail.
    order = orders_list[-1]
    assert order["data_key"] == "None"
    assert order["venue"] == "None"
    assert order["group_id"] == "None"
    assert order["leg_key"] == "None"


def test_save_lt_order_document_has_new_schema_no_tradingsymbol(monkeypatch):
    monkeypatch.setattr(live, "send_order_alert", lambda *a, **k: None)
    db, redis_cursor = FakeDB(), FakeRedis()

    status, orders_list = live.save_lt_order(
        app_db_cursor=db, redis_cursor=redis_cursor, orders_list=[], symbol="NIFTY_23450_CE",
        quantity=25, user_id="u1", strategy_id="s1", request_id="r1", exchange="NFO",
        exchange_timestamp=datetime.datetime(2026, 1, 1, 9, 20), order_id="OID1",
        data_key="UPSTOX:XNSE:NIFTY_23450_CE", venue="XNSE", group_id="r1:1", leg_key="CE",
        broker="zerodha", broker_symbol="NIFTY26AUG23450CE")

    assert status == "success"
    order = orders_list[-1]
    assert "tradingsymbol" not in order
    assert order["symbol"] == "NIFTY_23450_CE"
    assert order["venue"] == "XNSE"
    assert order["data_key"] == "UPSTOX:XNSE:NIFTY_23450_CE"
    assert order["group_id"] == "r1:1"
    assert order["leg_key"] == "CE"
    assert order["broker"] == "zerodha"
    assert order["broker_symbol"] == "NIFTY26AUG23450CE"
    assert order["exchange"] == "NFO"  # kept for brokerage/OMS until Track B2


def test_save_lt_order_broker_fields_default_none(monkeypatch):
    """ broker/broker_symbol are filled later from the OMS response (Track
    B2) — for now we just store whatever's passed, default None. """
    monkeypatch.setattr(live, "send_order_alert", lambda *a, **k: None)
    db, redis_cursor = FakeDB(), FakeRedis()

    _, orders_list = live.save_lt_order(
        app_db_cursor=db, redis_cursor=redis_cursor, orders_list=[], symbol="NIFTY_23450_CE",
        quantity=25, user_id="u1", strategy_id="s1", request_id="r1",
        exchange_timestamp=datetime.datetime(2026, 1, 1, 9, 20), order_id="OID1")

    # Round-tripped through the (fake) Redis list, so None comes back as the
    # string "None" like every other unset field here -- not a schema detail.
    order = orders_list[-1]
    assert order["broker"] == "None"
    assert order["broker_symbol"] == "None"


def test_place_bt_order_document_renamed_field():
    orders_list = []
    from trigerr.orders import backtest
    candle = {"close": 100, "timestamp": datetime.datetime(2026, 1, 1, 9, 20),
             "date": datetime.datetime(2026, 1, 1), "symbol": "NIFTY_23450_CE"}
    result = backtest.place_bt_order(order_candle=candle, quantity=25, orders_list=orders_list)
    assert "tradingsymbol" not in result[-1]
    assert result[-1]["symbol"] == "NIFTY_23450_CE"


# ---------------------------------------------------------------------------
# 2. Readers — check_open_orders / check_existing_order / convert_to_trades
# ---------------------------------------------------------------------------

def _entry_order(symbol="NIFTY_23450_CE", data_key="UPSTOX:XNSE:NIFTY_23450_CE", group_id="r1:1", **extra):
    order = {
        "symbol": symbol, "data_key": data_key, "group_id": group_id,
        "trade_action": "ENTRY", "date": datetime.datetime(2026, 1, 1), "day": "Thursday",
        "order_timestamp": "2026-01-01 09:20:00", "trigger_price": 100, "quantity": 25,
        "lot_size": 25, "investment": 2500, "position_type": "SHORT", "exchange": "NFO",
        "market": "IN", "order_type": "MARKET",
        "user_id": "507f1f77bcf86cd799439011", "strategy_id": "507f1f77bcf86cd799439012",
        "request_id": "507f1f77bcf86cd799439013",
    }
    order.update(extra)
    return order


def _exit_order(symbol="NIFTY_23450_CE", exit_type="T1", trigger_price=90, quantity=25, **extra):
    order = {
        "symbol": symbol, "trade_action": "EXIT", "exit_type": exit_type,
        "order_timestamp": "2026-01-01 09:25:00", "trigger_price": trigger_price, "quantity": quantity,
        "position_type": "SHORT", "order_type": "MARKET",
    }
    order.update(extra)
    return order


def test_check_open_orders_works_off_symbol():
    orders_list = [_entry_order(quantity_left=25), _exit_order(quantity_left=0)]
    open_orders = orders_utils.check_open_orders(orders_list)
    assert open_orders == {}  # fully exited -> not open

    still_open = [_entry_order(quantity_left=25)]
    open_orders = orders_utils.check_open_orders(still_open)
    assert "NIFTY_23450_CE" in open_orders


def test_check_existing_order_works_off_symbol():
    orders_list = [_exit_order()]
    assert orders_utils.check_existing_order(
        symbol="NIFTY_23450_CE", exit_type="T1", orders_list=orders_list,
        entry_time="2026-01-01 09:20:00") is True
    assert orders_utils.check_existing_order(
        symbol="OTHER_SYMBOL", exit_type="T1", orders_list=orders_list,
        entry_time="2026-01-01 09:20:00") is False


def test_convert_to_trades_carries_symbol_data_key_group_id():
    orders_list = [_entry_order(quantity_left=0), _exit_order(exit_type="T1", quantity_left=0)]
    trades = orders_utils.convert_to_trades(
        orders_list=orders_list, market_type="options", order_exit_levels=["T1"],
        mode="vt", broker="zerodha")
    assert len(trades) == 1
    trade = trades[0]
    assert trade["stock"] == "NIFTY_23450_CE"
    assert trade["symbol"] == "NIFTY_23450_CE"
    assert trade["data_key"] == "UPSTOX:XNSE:NIFTY_23450_CE"
    assert trade["group_id"] == "r1:1"


# ---------------------------------------------------------------------------
# 3. sequence() — multi-leg BUY-before-SELL (spec §8.2)
# ---------------------------------------------------------------------------

def test_sequence_puts_every_buy_before_every_sell():
    orders = [{"transaction_type": "SELL", "leg": "a"}, {"transaction_type": "BUY", "leg": "b"},
             {"transaction_type": "SELL", "leg": "c"}, {"transaction_type": "BUY", "leg": "d"}]
    result = orders_utils.sequence(orders)
    assert [o["transaction_type"] for o in result] == ["BUY", "BUY", "SELL", "SELL"]


def test_sequence_is_stable_within_a_side():
    orders = [{"transaction_type": "BUY", "leg": "b1"}, {"transaction_type": "BUY", "leg": "b2"},
             {"transaction_type": "SELL", "leg": "s1"}, {"transaction_type": "SELL", "leg": "s2"}]
    result = orders_utils.sequence(orders)
    assert [o["leg"] for o in result] == ["b1", "b2", "s1", "s2"]


def test_sequence_iron_fly_wings_before_shorts_regardless_of_authored_order():
    """ Iron fly: SELL CE, SELL PE (the shorts), BUY CE wing, BUY PE wing —
    authored in any order, both wings must sequence first. """
    orders = [{"transaction_type": "SELL", "leg": "short_ce"}, {"transaction_type": "SELL", "leg": "short_pe"},
             {"transaction_type": "BUY", "leg": "wing_ce"}, {"transaction_type": "BUY", "leg": "wing_pe"}]
    result = orders_utils.sequence(orders)
    assert [o["leg"] for o in result] == ["wing_ce", "wing_pe", "short_ce", "short_pe"]

    # authored with the wings interleaved -> still both wings first, stable within side
    orders2 = [{"transaction_type": "BUY", "leg": "wing_ce"}, {"transaction_type": "SELL", "leg": "short_ce"},
              {"transaction_type": "SELL", "leg": "short_pe"}, {"transaction_type": "BUY", "leg": "wing_pe"}]
    result2 = orders_utils.sequence(orders2)
    assert [o["leg"] for o in result2] == ["wing_ce", "wing_pe", "short_ce", "short_pe"]
