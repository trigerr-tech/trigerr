""" The position manager against the REAL order service: the SDK's HTTP calls go into the order service's own app
(trigerr-orders-api, checked out beside this repo), with its real order_utils and Dhan adapter. Only the true edges
are faked: Dhan's REST API, Mongo and Redis. Earlier tests of the live order path answered for the order service
with made-up replies and hid two real bugs; these do not.

Skipped when the order service is not checked out beside this repo. """
import json
import os
import sys
import threading
from pathlib import Path

import pytest
import requests

from trigerr.orders import live, positions
from test_orders_schema import FakeDB

OMS_ROOT = Path(__file__).resolve().parents[2] / "trigerr-orders-api"
pytestmark = pytest.mark.skipif(not (OMS_ROOT / "trigerr_orders_api.py").exists(), reason="trigerr-orders-api is not beside this repo")

LOT = 75
REQUEST_ID = "req-1"


class StateRedis:
    """ The few commands the SDK uses on the state Redis: the orders list, the position books, the request lock. """
    def __init__(self):
        self.lists, self.hashes, self.values, self.fail_rpush = {}, {}, {}, 0

    def rpush(self, key, value):
        if self.fail_rpush:
            self.fail_rpush -= 1
            raise ConnectionError("socket closed")
        self.lists.setdefault(key, []).append(value)
        return len(self.lists[key])

    def lrange(self, key, start, end):
        values = self.lists.get(key, [])
        return values[start:] if end == -1 else values[start:end + 1]

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        self.values.pop(key, None)

    def expire(self, key, ttl):
        pass

    def publish(self, channel, message):
        pass


@pytest.fixture(scope="module")
def oms():
    os.environ.setdefault("CONFIG_JSON_FILE", str(OMS_ROOT / "tests" / "fixtures" / "config_stub.json"))
    for path in (str(OMS_ROOT), str(OMS_ROOT / "tests")):
        if path not in sys.path:
            sys.path.append(path)
    import encrypted_docs
    import instruments
    import order_utils
    import test_dhan_roundtrip as roundtrip
    import trigerr_orders_api as api
    from brokers import broker_dhan
    from fastapi.testclient import TestClient
    from test_idempotency import FakeAsyncRedis
    if hasattr(api, "order_ledger"):
        # The order ledger writes to Mongo from a background thread, and there is no Mongo here. Left on, its first
        # write wakes pymongo's own helper threads, which call time.sleep in a loop: with sleep replaced by the test
        # clock below, they make that clock run away.
        api.order_ledger.stop()
    return {"api": api, "order_utils": order_utils, "roundtrip": roundtrip, "broker_dhan": broker_dhan, "instruments": instruments,
            "fernet": encrypted_docs.FERNET, "encrypted": encrypted_docs.encrypted, "TestClient": TestClient, "FakeAsyncRedis": FakeAsyncRedis}


class World:
    """ One test's order service, broker, state Redis, Mongo and clock, and the position under test. """


@pytest.fixture
def world(oms, monkeypatch):
    api, roundtrip = oms["api"], oms["roundtrip"]
    api._broker_context_cache.clear()
    oms["instruments"]._instrument_cache.clear()
    monkeypatch.setattr(api, "_fernet", oms["fernet"])
    w = World()
    w.script = []            # what Dhan does with each new order, in turn: "fill", ("part", units), "reject", "open"
    w.lose_answers = 0       # this many SDK calls to /place_order get no answer
    w.deliver_lost = True    # ... though the order service did (True) or did not (False) receive them
    w.clock = 1_000_000.0
    dhan = w.dhan = roundtrip.FakeDhan()

    def dhan_request(method, url, headers=None, json=None, timeout=None):
        reply = dhan(method, url, headers=headers, json=json, timeout=timeout)
        if (method, url) == ("POST", roundtrip.BASE + "/orders"):
            order_id = str(dhan.next_id)
            behaviour = w.script.pop(0) if w.script else "fill"
            if behaviour == "fill":
                dhan.fill(order_id, 100.0)
            elif behaviour == "reject":
                dhan.orders[order_id]["orderStatus"] = "REJECTED"
            elif behaviour != "open":
                dhan.orders[order_id].update(orderStatus="CANCELLED", filledQty=behaviour[1], averageTradedPrice=100.0)
        return reply

    monkeypatch.setattr(oms["broker_dhan"].requests, "request", dhan_request)
    monkeypatch.setattr(api, "state_redis", oms["FakeAsyncRedis"]())
    monkeypatch.setattr(api.broker_credentials_coll, "find_one", lambda query, **k: oms["encrypted"](roundtrip.CRED_DOC))
    monkeypatch.setattr(api.symbols_coll, "find_one", lambda query, **k: roundtrip.SYMBOL_DOC if query["symbol"] == roundtrip.SYMBOL else None)
    client = oms["TestClient"](api.app)

    class Reply:
        def __init__(self, response):
            self.status_code, self.body = response.status_code, response.json()

        def json(self):
            return self.body

    def to_oms(url, json=None, headers=None, timeout=None):
        path = "/" + url.rsplit("/", 1)[1]
        if path == "/place_order" and w.lose_answers:
            w.lose_answers -= 1
            if w.deliver_lost:
                client.post(path, json=json)
            raise requests.ConnectionError("no answer")
        return Reply(client.post(path, json=json))

    real_sleep = live.time.sleep

    def tick(seconds=1):
        # pymongo's helper threads sleep in a loop; they must not turn this test's clock.
        if threading.current_thread().name.startswith("pymongo"):
            return real_sleep(seconds)
        w.clock += seconds

    monkeypatch.setattr(live, "orders_url", "http://oms/")
    monkeypatch.setattr(live.requests, "post", to_oms)
    monkeypatch.setattr(live, "send_order_alert", lambda alert: None)
    for module in (live.time, positions.time, oms["order_utils"].time, oms["broker_dhan"].time):
        monkeypatch.setattr(module, "sleep", tick)
        monkeypatch.setattr(module, "time", lambda: w.clock)
    w.state, w.db, w.events = StateRedis(), FakeDB(), []
    w.position = positions.position_handle(
        state_cursor=w.state, app_db_cursor=w.db, request_id=REQUEST_ID, group_id=f"{REQUEST_ID}:1", leg_key="CE",
        credential_id=roundtrip.CRED_ID, symbol=roundtrip.SYMBOL, exchange="NFO", lot_size=LOT, position_type="LONG",
        order_fields={"venue": "XNSE", "asset_type": "OPTIONS", "holding_type": "INTRADAY"},
        record_fields={"user_id": "u1", "strategy_id": "s1", "market_type": "options"},
        entry_fields=lambda price, lots: {"sl_price": price - 10, "investment": price * lots * LOT},
        on_event=lambda name, details: w.events.append(name))
    w.lines = lambda: [json.loads(raw) for raw in w.state.lists.get(f"{REQUEST_ID}_orders", [])]
    w.exits = lambda: [(line["exit_type"], line["quantity"], line["quantity_left"]) for line in w.lines() if line["trade_action"] == "EXIT"]
    w.book = lambda: positions.read_book(w.position)["orders"]
    w.tick = tick
    return w


def opened(world, lots=4):
    assert positions.open_position(world.position, lots)["state"] == "done"
    return world.position


# ----------------------------------------------------------------------------------------------------------- entries

def test_an_entry_that_fills_is_done_and_recorded_once(world):
    result = positions.open_position(world.position, 4)
    assert (result["state"], result["filled"], result["price"], result["held"]) == ("done", 4, 100.0, 4)
    [entry] = world.lines()
    assert (entry["trade_action"], entry["quantity"], entry["quantity_left"], entry["trigger_price"]) == ("ENTRY", 4, 4, 100.0)
    assert entry["sl_price"] == 90.0 and entry["order_id"].startswith("order_") and entry["broker"] == "dhan"
    assert len(world.db["lt_orders"].docs) == 1 and world.book() == []


def test_an_entry_that_fills_in_part_is_taken_at_what_filled(world):
    world.script = [("part", 2 * LOT)]
    result = positions.open_position(world.position, 4)
    assert (result["state"], result["filled"], result["held"]) == ("part", 2, 2)
    assert world.lines()[0]["quantity"] == 2


def test_an_entry_that_is_refused_holds_nothing(world):
    world.script = ["reject"]
    result = positions.open_position(world.position, 4)
    assert (result["state"], result["held"]) == ("nothing", 0) and world.lines() == [] and world.book() == []


def test_an_entry_still_open_is_working_and_a_later_sync_takes_its_fill(world):
    world.script = ["open"]
    result = positions.open_position(world.position, 4, wait_s=3)
    assert (result["state"], result["held"], result["working_entry"]) == ("working", 0, 4)
    assert positions.open_position(world.position, 4)["note"].startswith("the position is already open"), "no second entry"
    assert len(world.dhan.orders) == 1

    world.dhan.fill(next(iter(world.dhan.orders)), 101.0)
    result = positions.sync_position(world.position)
    assert (result["state"], result["held"], result["working_entry"]) == ("nothing", 4, 0)
    assert world.lines()[0]["trigger_price"] == 101.0


def test_a_market_order_open_too_long_is_cancelled_by_sync(world):
    world.script = ["open"]
    positions.open_position(world.position, 4, wait_s=3)
    world.tick(positions.MARKET_PATIENCE_S)
    assert positions.sync_position(world.position)["state"] == "working"
    assert "cancel_sent" in world.events
    result = positions.sync_position(world.position)
    assert (result["state"], result["held"], result["working_entry"]) == ("nothing", 0, 0) and world.book() == []


# ------------------------------------------------------------------------------------------------------------- exits

def test_an_exit_that_fills_is_recorded_under_its_reason(world):
    opened(world)
    result = positions.reduce_position(world.position, 1, "T1")
    assert (result["state"], result["filled"], result["held"]) == ("done", 1, 3)
    result = positions.close_position(world.position, "SL")
    assert (result["state"], result["filled"], result["held"]) == ("done", 3, 0)
    assert world.exits() == [("T1", 1, 3), ("SL", 3, 0)]
    assert len(world.db["lt_orders"].docs) == 3


def test_an_exit_that_fills_in_part_is_sent_again_for_the_rest(world):
    opened(world)
    world.script = [("part", 1 * LOT), "fill"]
    result = positions.close_position(world.position, "SL")
    assert (result["state"], result["filled"], result["held"]) == ("done", 4, 0)
    assert world.exits() == [("SL_PART", 1, 3), ("SL", 3, 0)]


def test_an_exit_that_keeps_filling_in_part_stops_after_three_orders(world):
    opened(world)
    world.script = [("part", LOT)] * 5
    result = positions.close_position(world.position, "SL")
    assert (result["state"], result["filled"], result["held"]) == ("part", 3, 1)
    assert len(world.dhan.orders) == 1 + positions.EXIT_ORDERS_PER_REQUEST


def test_no_second_exit_for_lots_an_open_exit_already_covers(world):
    opened(world)
    world.script = ["open"]
    result = positions.reduce_position(world.position, 3, "T1", wait_s=3)
    assert (result["state"], result["held"], result["working_exit"]) == ("working", 4, 3)

    result = positions.reduce_position(world.position, 4, "SL", wait_s=3)
    assert (result["filled"], result["held"], result["working_exit"]) == (1, 3, 3), "only the lot the open exit does not cover"
    assert positions.reduce_position(world.position, 4, "SL", wait_s=3)["note"].startswith("nothing is free to exit")
    assert len(world.dhan.orders) == 3      # the entry, the open exit, the one-lot exit


def test_close_cancels_the_open_exit_first_and_exits_everything_once(world):
    opened(world)
    world.script = ["open"]
    positions.reduce_position(world.position, 3, "T1", wait_s=3)
    result = positions.close_position(world.position, "SL")
    assert (result["state"], result["filled"], result["held"], result["working_exit"]) == ("done", 4, 0, 0)
    assert world.exits() == [("SL", 4, 0)]


def test_an_exit_whose_answer_was_lost_is_found_by_its_key_at_once(world):
    opened(world)
    world.lose_answers = 99
    result = positions.close_position(world.position, "SL")
    assert (result["state"], result["filled"], result["held"]) == ("done", 4, 0)
    assert world.exits() == [("SL", 4, 0)] and len(world.dhan.orders) == 2


def test_an_exit_whose_result_is_not_known_is_never_sent_twice(world):
    """ The order reached the broker and filled, but its answer was lost and then the order service could not be asked. """
    opened(world)
    world.lose_answers = 99
    real_find = live.find_live_order
    live.find_live_order = lambda key, void=False: None
    try:
        result = positions.close_position(world.position, "SL", wait_s=3)
        assert (result["state"], result["held"], result["working_exit"]) == ("working", 4, 4)
        again = positions.close_position(world.position, "SL", wait_s=3)
        assert again["note"].startswith("nothing is free to exit") and len(world.dhan.orders) == 2
        world.tick(positions.ATTENTION_AFTER_S)
        assert positions.sync_position(world.position)["state"] == "unknown"
    finally:
        live.find_live_order = real_find
    result = positions.sync_position(world.position)
    assert (result["held"], result["working_exit"]) == (0, 0)
    assert world.exits() == [("SL", 4, 0)] and len(world.dhan.orders) == 2


def test_an_exit_that_never_reached_the_order_service_ends_with_nothing_and_can_be_sent_again(world):
    opened(world)
    world.lose_answers, world.deliver_lost = 99, False
    result = positions.close_position(world.position, "SL")
    assert (result["state"], result["held"], result["working_exit"]) == ("nothing", 4, 0)
    assert len(world.dhan.orders) == 1
    world.lose_answers = 0
    assert positions.close_position(world.position, "SL")["state"] == "done" and world.exits() == [("SL", 4, 0)]


# ----------------------------------------------------------------------------------------------------------- records

def test_a_fill_that_cannot_be_put_in_the_orders_list_stays_counted_and_is_recorded_by_a_later_sync(world):
    opened(world)
    world.state.fail_rpush = 3
    result = positions.close_position(world.position, "SL")
    assert result["not_recorded"] and (result["held"], result["working_exit"]) == (4, 4)
    assert positions.close_position(world.position, "SL")["note"].startswith("nothing is free to exit")
    result = positions.sync_position(world.position)
    assert (result["held"], result["working_exit"]) == (0, 0) and world.exits() == [("SL", 4, 0)]
    assert len(world.dhan.orders) == 2, "the exit was sent once"


def test_a_fill_already_in_the_orders_list_is_not_recorded_twice(world):
    opened(world)
    saved_books = []
    real_write = positions.write_book

    def remember(handle, book):
        saved_books.append(json.dumps(book, default=str))
        real_write(handle, book)

    positions.write_book = remember
    try:
        positions.close_position(world.position, "SL")
    finally:
        positions.write_book = real_write
    # The task dies after the line was saved but before the book said so: the book is back at "ended, not booked".
    stale = next(raw for raw in reversed(saved_books) if any(o["ended"] and not o["booked"] for o in json.loads(raw)["orders"]))
    world.state.hset(f"{REQUEST_ID}_positions", positions.book_field(world.position), stale)
    positions.sync_position(world.position)
    assert world.exits() == [("SL", 4, 0)] and world.book() == []


def test_a_request_is_busy_while_another_actor_holds_the_lock(world, monkeypatch):
    opened(world)
    world.state.set(f"{REQUEST_ID}:exit_mutex", "someone-else")
    monkeypatch.setattr(positions, "acquire_exit_mutex", lambda cursor, request_id: None)
    assert positions.close_position(world.position, "SL")["state"] == "busy" and len(world.dhan.orders) == 1


# ------------------------------------------------------------------------------------- with the risk engine enforcing

@pytest.fixture
def guarded(world, oms, monkeypatch):
    """ The same world, with the order service's risk engine switched to enforce and a Redis it can keep its book in.
    Skipped against an order service checkout that has no risk engine yet. """
    api = oms["api"]
    if not hasattr(api, "risk_check"):
        pytest.skip("this trigerr-orders-api checkout has no risk engine")
    from hash_redis import HashRedis
    monkeypatch.setattr(api, "state_redis", HashRedis())
    monkeypatch.setattr(api, "risk_mode", "enforce")
    monkeypatch.setattr(api, "risk_platform_contract_cap", None)
    monkeypatch.setattr(api, "risk_limits_default", {"max_order_value": 40_000, "max_open_value": 40_000, "max_daily_loss": 5_000,
                                                     "max_entries_per_day": 2})
    monkeypatch.setattr(api, "last_traded_price", lambda market, venue, symbol: 100.0)
    world.sent = []
    post = live.requests.post

    def recording(url, json=None, headers=None, timeout=None):
        if url.endswith("/place_order"):
            world.sent.append(json["order_params"].get("trade_action"))
        return post(url, json=json, headers=headers, timeout=timeout)

    monkeypatch.setattr(live.requests, "post", recording)
    return world


def test_the_manager_tells_the_order_service_entry_or_exit(guarded):
    opened(guarded)
    assert positions.close_position(guarded.position, "SL")["state"] == "done"
    assert guarded.sent == ["ENTRY", "EXIT"]


def test_an_entry_the_risk_engine_refuses_holds_nothing_and_reaches_no_broker(guarded):
    result = positions.open_position(guarded.position, 6)          # 6 lots x 75 x 100 = 45,000 > 40,000
    assert (result["state"], result["held"]) == ("nothing", 0)
    assert guarded.dhan.orders == {} and guarded.lines() == [] and guarded.book() == []


def test_a_full_trade_passes_and_the_exit_goes_out_though_the_account_is_then_reduce_only(guarded, oms):
    import asyncio
    api = oms["api"]
    opened(guarded)
    asyncio.run(api.risk_engine.write_state(api.state_redis, oms["roundtrip"].CRED_ID, "reduce_only", "admin", "test", guarded.clock))
    assert positions.close_position(guarded.position, "SL")["state"] == "done"
    assert guarded.exits() == [("SL", 4, 0)]
    again = positions.open_position(guarded.position, 1)
    assert again["state"] == "nothing" and len(guarded.dhan.orders) == 2


def test_a_run_may_not_enter_more_often_than_its_limit(guarded):
    for round_number in range(2):
        opened(guarded, lots=1)
        assert positions.close_position(guarded.position, "SL")["state"] == "done"
    third = positions.open_position(guarded.position, 1)
    assert third["state"] == "nothing" and len(guarded.dhan.orders) == 4


def test_every_look_at_the_position_marks_the_run_as_watching(world):
    key = positions.WATCH_KEY.format(request_id=REQUEST_ID)
    assert key not in world.state.values
    opened(world)
    first = world.state.values[key]
    world.tick(60)
    positions.sync_position(world.position)
    assert world.state.values[key] == first + 60


def test_the_order_service_knows_whose_order_it_is_and_whether_the_run_still_watches(guarded, oms):
    api = oms["api"]
    if not hasattr(api, "risk_compare"):
        pytest.skip("this trigerr-orders-api checkout has no compare endpoint")
    opened(guarded)
    client = oms["TestClient"](api.app)
    seen = client.get(f"/risk/compare/{oms['roundtrip'].CRED_ID}").json()["data"]
    assert seen["positions"][0]["requests"] == [REQUEST_ID] and seen["positions"][0]["held"] == 4 * LOT
    # The run's mark is in the SDK's state Redis; the order service reads the same Redis in production.
    assert positions.WATCH_KEY == api.risk_engine.WATCH_KEY


# ----------------------------------------------------------------------------------- the protective stop at the broker

def stop_orders(world):
    return [order for order in world.dhan.orders.values() if order["orderType"] == "STOP_LOSS"]


def protected(world, lots=4):
    """ An open position of `lots` with its stop resting at the broker: trigger 60, limit 50. """
    opened(world, lots)
    world.script = ["open"]
    result = positions.protect_position(world.position, "SL", 60.0, 50.0)
    assert result["protected"] == lots, result
    return result


def test_a_protective_stop_rests_at_the_broker_and_is_not_an_order_in_flight(world):
    result = protected(world)
    stop, = stop_orders(world)
    assert (stop["transactionType"], stop["quantity"], stop["triggerPrice"], stop["price"], stop["orderStatus"]) == ("SELL", 4 * LOT, 60.0, 50.0, "PENDING")
    assert (result["held"], result["working_exit"], result["protection_lost"]) == (4, 0, False)
    world.tick(3600)                                           # an hour later it still rests, and nobody is told to look
    later = positions.sync_position(world.position)
    assert (later["state"], later["protected"], later["working_exit"]) == ("nothing", 4, 0) and world.exits() == []


def test_asking_again_with_the_same_prices_places_no_second_stop(world):
    protected(world)
    again = positions.protect_position(world.position, "SL", 60.0, 50.0)
    assert again["protected"] == 4 and len(stop_orders(world)) == 1


def test_new_prices_take_the_old_stop_off_and_place_a_new_one(world):
    protected(world)
    world.script = ["open"]
    moved = positions.protect_position(world.position, "SL", 80.0, 70.0)
    old, new = stop_orders(world)
    assert moved["protected"] == 4 and old["orderStatus"] == "CANCELLED" and (new["triggerPrice"], new["price"], new["orderStatus"]) == (80.0, 70.0, "PENDING")
    assert moved["protection_lost"] is False and "protection_lost" not in world.events


def test_a_stop_that_fills_by_itself_closes_the_position_under_the_strategys_stop_name(world):
    protected(world)
    world.dhan.fill(stop_orders(world)[0]["orderId"], 55.0)
    result = positions.sync_position(world.position)
    assert (result["held"], result["protected"], result["protection_lost"]) == (0, 0, False)
    assert world.exits() == [("SL", 4, 0)] and world.lines()[-1]["trigger_price"] == 55.0 and world.book() == []


def test_a_part_exit_takes_the_stop_off_exits_and_puts_it_back_for_what_is_left(world):
    protected(world)
    world.script = ["fill", "open"]                            # the exit fills; the new stop rests
    result = positions.reduce_position(world.position, 1, "T1")
    old, new = stop_orders(world)
    assert (result["state"], result["filled"], result["held"], result["protected"], result["working_exit"]) == ("done", 1, 3, 3, 0)
    assert old["orderStatus"] == "CANCELLED" and (new["quantity"], new["triggerPrice"], new["price"], new["orderStatus"]) == (3 * LOT, 60.0, 50.0, "PENDING")
    assert world.exits() == [("T1", 1, 3)] and sides(world) == ["BUY", "SELL", "SELL", "SELL"]


def sides(world):
    return [order["transactionType"] for order in world.dhan.orders.values()]


def test_closing_takes_the_stop_off_first_and_leaves_none_behind(world):
    protected(world)
    result = positions.close_position(world.position, "T1")
    stop, = stop_orders(world)
    assert (result["state"], result["held"], result["protected"]) == ("done", 0, 0) and stop["orderStatus"] == "CANCELLED"
    assert world.exits() == [("T1", 4, 0)] and world.book() == [] and "protection_lost" not in world.events


def test_a_stop_that_filled_before_it_could_be_taken_off_is_counted_and_nothing_is_sold_twice(world):
    """ The stop triggers and fills in the moment the strategy decides to exit. Dhan refuses to cancel a traded order. """
    protected(world)
    stop_id = stop_orders(world)[0]["orderId"]
    world.dhan.fill(stop_id, 55.0)
    result = positions.close_position(world.position, "T1")
    assert result["held"] == 0 and world.exits() == [("SL", 4, 0)] and sides(world) == ["BUY", "SELL"]


def test_a_stop_the_broker_refuses_is_reported_as_lost_protection(world):
    opened(world)
    world.script = ["reject"]
    result = positions.protect_position(world.position, "SL", 60.0, 50.0)
    assert result["protected"] == 0 and result["protection_lost"] is True and result["held"] == 4 and "protection_lost" in world.events


def test_a_resting_stop_the_exchange_throws_out_is_reported_once_and_the_position_is_still_held(world):
    protected(world)
    stop_orders(world)[0]["orderStatus"] = "REJECTED"          # thrown out when it triggered: limit outside the allowed range
    result = positions.sync_position(world.position)
    assert (result["held"], result["protected"], result["protection_lost"]) == (4, 0, True) and world.exits() == []
    assert positions.sync_position(world.position)["protection_lost"] is False and world.events.count("protection_lost") == 1


def test_a_stop_left_behind_by_a_position_someone_else_closed_is_taken_off(world):
    protected(world)
    entry = world.lines()[0]
    world.state.lists[f"{REQUEST_ID}_orders"].append(json.dumps(dict(entry, trade_action="EXIT", exit_type="MANUAL", quantity_left=0)))
    result = positions.sync_position(world.position)
    assert result["held"] == 0 and result["protected"] == 0 and stop_orders(world)[0]["orderStatus"] == "CANCELLED"
    assert "stop_covers_more_than_held" in world.events and "protection_lost" not in world.events


@pytest.mark.parametrize("trigger, limit", [(50.0, 60.0), (0, 50.0), (60.0, None)])
def test_a_stop_on_the_wrong_side_or_without_a_price_is_refused_before_anything_is_sent(world, trigger, limit):
    opened(world)
    with pytest.raises(ValueError):
        positions.protect_position(world.position, "SL", trigger, limit)
    assert stop_orders(world) == []


def test_nothing_held_means_nothing_to_protect(world):
    result = positions.protect_position(world.position, "SL", 60.0, 50.0)
    assert result["protected"] == 0 and "nothing to protect" in result["note"] and world.dhan.orders == {}


def test_with_the_risk_engine_enforcing_the_stop_and_the_exit_after_it_both_go_out(guarded):
    protected(guarded)
    guarded.script = ["fill", "open"]
    assert positions.reduce_position(guarded.position, 2, "T1")["protected"] == 2
    assert positions.close_position(guarded.position, "SL")["held"] == 0
    assert guarded.sent == ["ENTRY", "EXIT", "EXIT", "EXIT", "EXIT"] and guarded.exits() == [("T1", 2, 2), ("SL", 2, 0)]


def test_the_stop_covers_only_the_lots_no_exit_order_already_covers(world):
    opened(world)
    world.script = ["open", "open"]                            # an exit of 2 that is still open, then the stop
    assert positions.reduce_position(world.position, 2, "T1")["working_exit"] == 2
    result = positions.protect_position(world.position, "SL", 60.0, 50.0)
    assert (result["protected"], result["working_exit"]) == (2, 2) and stop_orders(world)[0]["quantity"] == 2 * LOT
