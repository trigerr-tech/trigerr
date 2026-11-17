""" The position manager: the one place a live position's orders are sent, followed and recorded.

A strategy asks (open_position, reduce_position, close_position, cancel_working, sync_position) and reads the
answer. It holds no order handling of its own.

Each position has a book in the state Redis (hash `{request_id}_positions`, field `{group_id}|{leg_key}`): the
orders sent for it, each under a key written to the book BEFORE the order goes out. An order is followed until it
has ended at the broker; what it filled is then booked: one line in the request's orders list and in Mongo, in the
format every reader already uses (save_lt_order).

What is held is read from the orders list, as everywhere else, so a manual exit written there by the order service
is seen. The book adds what the list cannot know: orders still in flight. An exit is never sent for more than
    held - lots of exit orders not yet booked
and an order whose result is not known counts in full. A second exit on top of one that may still fill is
therefore not possible, while the lots it does not cover can still be exited.

Every request returns at once with an answer (see `answer`). A market order usually ends inside the request. One
that does not is still working: the caller calls sync_position on its next candle, which follows it, cancels what
is open of it after MARKET_PATIENCE_S, and books what it filled. Nothing here remembers anything outside the book,
so any actor holding the cursors (a restarted task, a watcher) can sync the same position.

Live only. See POSITION_MANAGER_DESIGN.md. """
import datetime
import json
import time
import uuid

from trigerr.orders import live
from trigerr.orders.orders_utils import (acquire_exit_mutex, check_open_orders, fetch_orders_list, release_exit_mutex,
                                         renew_exit_mutex)

# How long a request waits for its order to end before answering "working".
REQUEST_WAIT_S = 10
# A market order still open this long after it was sent has what is open of it cancelled.
MARKET_PATIENCE_S = 60
# After a part fill an exit is sent again for the rest, this many orders at most per request.
EXIT_ORDERS_PER_REQUEST = 3
# How long a request looks at a protective stop it has just placed, to see whether the broker took it or refused it.
STOP_LOOK_S = 3
# An order whose result has been unknown this long is reported as needing a person.
ATTENTION_AFTER_S = 180
# A fill that covers only part of the exit it was sent for is recorded under the exit's name plus this: the trade
# record is closed by the name of its last exit (convert_to_trades), so a part must not carry it.
PART_SUFFIX = "_PART"
BOOK_TTL_S = 20 * 60 * 60
EXIT_SIDE = {"LONG": "SELL", "SHORT": "BUY"}
ENTRY_SIDE = {"LONG": "BUY", "SHORT": "SELL"}


def position_handle(state_cursor, app_db_cursor, request_id, group_id, leg_key, credential_id, symbol, exchange, lot_size,
                    position_type, order_fields=None, record_fields=None, entry_fields=None, on_event=None):
    """ What every request needs to know about one position.
    order_fields  - extra keyword arguments for place_lt_order (asset_type, validity, holding_type, underlying, max_qpo, venue).
    record_fields - extra keyword arguments for save_lt_order on every line (params, market_type, user_id, strategy_id, ...).
    entry_fields  - called as entry_fields(price, lots) when the entry is booked; returns the `params` of the entry line
                    (the numbers a strategy works out from its fill: stop, targets, investment).
    on_event      - called as on_event(name, details) for each thing that happens to the position. """
    if not group_id or not leg_key:
        raise ValueError(f"a position is found by its group_id and leg_key, got {group_id!r} and {leg_key!r}")
    return {"state_cursor": state_cursor, "app_db_cursor": app_db_cursor, "request_id": str(request_id), "group_id": group_id,
            "leg_key": leg_key, "credential_id": str(credential_id), "symbol": symbol, "exchange": exchange,
            "lot_size": lot_size, "position_type": position_type, "order_fields": dict(order_fields or {}),
            "record_fields": dict(record_fields or {}), "entry_fields": entry_fields, "on_event": on_event}


def tell(handle, name, **details):
    print(f"position {handle['request_id']} {handle['group_id']}|{handle['leg_key']} : {name} {details}")
    if handle["on_event"]:
        handle["on_event"](name, details)


def owner(handle):
    """ Whose position this is, as every call to the order service carries it. The manager says so itself on each call
    (place, status, cancel), so the order service's ledger notes of one run can be found by its request id whoever the
    caller is, with or without a logging context. """
    return {"request_id": handle["request_id"], "user_id": handle["record_fields"].get("user_id"),
            "strategy_id": handle["record_fields"].get("strategy_id")}


def book_field(handle):
    return f"{handle['group_id']}|{handle['leg_key']}"


def read_book(handle):
    raw = handle["state_cursor"].hget(f"{handle['request_id']}_positions", book_field(handle))
    return json.loads(raw) if raw else {"orders": []}


def write_book(handle, book):
    """ Raises when Redis refuses: an order must never go out, or be forgotten, without its line in the book. """
    key = f"{handle['request_id']}_positions"
    handle["state_cursor"].hset(key, book_field(handle), json.dumps(book, default=str))
    handle["state_cursor"].expire(key, BOOK_TTL_S)


def held_lots(handle):
    """ Lots the orders list says are held. Raises when the list cannot be read: "could not read" must not look like "flat". """
    orders_list = fetch_orders_list(redis_cursor=handle["state_cursor"], request_id=handle["request_id"])
    if orders_list is None:
        raise RuntimeError(f"the orders list of {handle['request_id']} could not be read")
    leg = check_open_orders(orders_list).get(handle["symbol"])
    return (leg["quantity_left"] if leg else 0), orders_list


def unbooked_lots(order):
    """ Lots of an order that are not in the orders list yet: all it asked for while it may still fill, what it filled once ended. """
    if order["booked"]:
        return 0
    return order["filled"] if order["ended"] else order["lots"]


def working_lots(book, side):
    return sum(unbooked_lots(order) for order in book["orders"] if order["side"] == side)


def send_order(handle, book, side, reason, lots, order_type, price, trigger=None, protect=False):
    """ Writes the order's key to the book, then sends it. Whatever the answer, the order is in the book and sync follows it.
    protect marks the position's protective stop: an exit that rests at the broker (see protect_position). """
    order = {"key": uuid.uuid4().hex, "side": side, "reason": reason, "lots": lots, "order_type": order_type, "order_id": None,
             "filled": 0, "price": 0.0, "ended": False, "booked": False, "sent_at": time.time()}
    if protect:
        order.update(protect=True, trigger=trigger, limit=price)
    book["orders"].append(order)
    write_book(handle, book)
    tell(handle, "order_planned", key=order["key"], side=side, reason=reason, lots=lots)
    sides = ENTRY_SIDE if side == "ENTRY" else EXIT_SIDE
    try:
        order_status, reply = live.place_lt_order(symbol=handle["symbol"], exchange=handle["exchange"], quantity=lots,
                                                  transaction_type=sides[handle["position_type"]], order_type=order_type,
                                                  lot_size=handle["lot_size"], credential_id=handle["credential_id"],
                                                  order_price=price, trigger_price=trigger, idempotency_key=order["key"], trade_action=side,
                                                  request_id=handle["request_id"], user_id=handle["record_fields"].get("user_id"),
                                                  strategy_id=handle["record_fields"].get("strategy_id"),
                                                  **handle["order_fields"])
    except Exception as e:
        order_status, reply = "failed", None
        print(f"Exception in placing order {order['key']} : {e}")
    order_id = live.placed_order_id(reply)
    if order_id:
        order.update(order_id=order_id, broker=reply.get("broker"), broker_symbol=reply.get("broker_symbol"))
        write_book(handle, book)
    # No order id: refused, never arrived, or not known. sync_order asks the order service which, by the key.
    tell(handle, "order_sent", key=order["key"], order_id=order_id, status=order_status)
    return order


def sync_order(handle, order):
    """ Brings one order of the book up to date from the order service. Changes the order in place; sends nothing but, for a
    market order open too long, a cancel. """
    if order["ended"]:
        return
    if not order["order_id"]:
        found = live.find_live_order(order["key"], void=True)
        if not found:
            return
        if found.get("found") == "none":
            order.update(ended=True, filled=0, note="the placement never reached the broker")
            return
        if found.get("found") != "placed":
            return      # still running in the order service, or it broke midway: not known yet
        placed = found.get("order") or {}
        order_id = live.placed_order_id(placed)
        if not order_id:
            order.update(ended=True, filled=0, note=str(placed.get("message") or "no piece of the order reached the broker"))
            return
        order.update(order_id=order_id, broker=placed.get("broker"), broker_symbol=placed.get("broker_symbol"))
    reply = live.order_status_now(handle["credential_id"], order["order_id"], handle["exchange"], **owner(handle))
    if not reply:
        return
    if reply.get("status") in live.ENDED_STATUSES:
        order.update(ended=True, filled=live.filled_lots(reply, handle["lot_size"]), price=reply.get("average_price") or 0.0,
                     reply=reply)
    elif reply.get("status") == "OPEN" and order["order_type"] == "MARKET" and time.time() - order["sent_at"] >= MARKET_PATIENCE_S:
        tell(handle, "cancel_sent", key=order["key"], order_id=order["order_id"])
        live.cancel_live_order(handle["credential_id"], order["order_id"], **owner(handle))


def book_ended_orders(handle, book):
    """ Records what each ended order filled: one line in the orders list and Mongo. An order already in the list (by its order
    id) is not recorded twice. Returns the save statuses that were not "success". """
    problems = []
    for order in book["orders"]:
        if order["booked"] or not order["ended"]:
            continue
        if order["filled"] <= 0:
            if order.get("protect") and not order.get("cancel_asked"):
                # Nobody here cancelled it: the broker or the exchange ended it (refused when placed, or thrown out when
                # it triggered because its limit was outside the allowed range). The position has no stop at the broker.
                problems.append("protection_lost")
                tell(handle, "protection_lost", key=order["key"], order_id=order["order_id"], note=order.get("note") or "")
            order.update(booked=True, reply=None)
            continue
        held, orders_list = held_lots(handle)
        action = "ENTRY" if order["side"] == "ENTRY" else "EXIT"
        if any(line.get("order_id") == order["order_id"] and line.get("trade_action") == action for line in orders_list):
            order.update(booked=True, reply=None)
            continue
        reply = order.get("reply") or {}
        stamp = datetime.datetime.strptime(str(reply["timestamp"]), '%Y-%m-%d %H:%M:%S') if reply.get("timestamp") else datetime.datetime.now().replace(microsecond=0)
        fields = dict(handle["record_fields"])
        if action == "ENTRY":
            lots, lots_left, exit_type, side = order["filled"], order["filled"], None, ENTRY_SIDE
            if handle["entry_fields"]:
                # Kept on the handle too: every later line of the position carries the entry's numbers.
                fields["params"] = handle["record_fields"]["params"] = handle["entry_fields"](order["price"], lots)
            else:
                tell(handle, "entry_booked_without_strategy_fields", key=order["key"])
        else:
            if order["filled"] > held:
                tell(handle, "exit_filled_more_than_held", key=order["key"], filled=order["filled"], held=held)
            lots, side = min(order["filled"], held), EXIT_SIDE
            lots_left = held - lots
            whole = order["filled"] >= order["lots"] or lots_left <= 0
            exit_type = order["reason"] if whole else order["reason"] + PART_SUFFIX
            if lots <= 0:
                order.update(booked=True, reply=None)
                continue
        save_status, _ = live.save_lt_order(
            app_db_cursor=handle["app_db_cursor"], redis_cursor=handle["state_cursor"], orders_list=orders_list,
            symbol=handle["symbol"], quantity=lots, quantity_left=lots_left, lot_size=handle["lot_size"],
            position_type=handle["position_type"], transaction_type=side[handle["position_type"]], trade_action=action,
            order_type=order["order_type"], exit_type=exit_type, trigger_price=order["price"], request_id=handle["request_id"],
            exchange=handle["exchange"], exchange_timestamp=stamp, order_id=order["order_id"], broker_response=reply,
            group_id=handle["group_id"], leg_key=handle["leg_key"], broker=order.get("broker"),
            broker_symbol=order.get("broker_symbol"), **fields)
        if save_status != "success":
            problems.append(save_status)
        if save_status == "failed":
            tell(handle, "fill_not_recorded", key=order["key"], order_id=order["order_id"], lots=lots)
            continue        # not in the orders list: stays unbooked, so its lots still count as working, and is tried again
        order.update(booked=True, reply=None)
        tell(handle, "fill_booked", key=order["key"], order_id=order["order_id"], action=action, lots=lots, price=order["price"],
             exit_type=exit_type, saved=save_status)
    return problems


def bring_up_to_date(handle, book):
    for order in book["orders"]:
        sync_order(handle, order)
    problems = book_ended_orders(handle, book)
    # Orders that are done with stay only while they explain something; the list is the record of what filled.
    book["orders"] = [order for order in book["orders"] if not order["booked"]]
    write_book(handle, book)
    return problems


def wait_for(handle, book, orders, wait_s, token):
    """ Follows `orders` until each has ended or wait_s is over, keeping the lock alive. """
    deadline = time.time() + wait_s
    while True:
        for order in orders:
            sync_order(handle, order)
        if all(order["ended"] for order in orders) or time.time() >= deadline:
            break
        renew_exit_mutex(handle["state_cursor"], handle["request_id"], token)
        time.sleep(1)
    write_book(handle, book)


def answer(handle, book, orders=(), problems=(), note="", asked=None):
    """ What a request tells its caller.
    state: "done"    - every order of the request ended and filled all that was asked
           "part"    - they ended and filled some of it
           "nothing" - they ended and filled none, or nothing was sent (see note)
           "working" - an order has not ended yet: call sync_position again
           "unknown" - an order's result has been unknown for ATTENTION_AFTER_S: a person should look
           "busy"    - someone else is acting on this request right now; nothing was done
    filled / price - lots the request's orders filled and their average price
    held           - lots the orders list says are held now
    working_entry / working_exit - lots of orders not yet in the orders list (counted in full while unknown)
    protected      - lots covered by the protective stop resting at the broker (not counted in working_exit)
    protection_lost - the protective stop ended without filling and nobody here cancelled it: the position has no stop
                     at the broker now
    record_gap     - a fill is in the orders list but not in Mongo
    not_recorded   - a fill could not be put in the orders list; it is counted as working and tried again on every sync """
    held, _ = held_lots(handle)
    filled = sum(order["filled"] for order in orders)
    # A request that sent several orders (the rest again after a part fill) asked once, for what its first order asked.
    asked = asked if asked is not None else sum(order["lots"] for order in orders)
    value = sum(order["filled"] * (order["price"] or 0) for order in orders)
    # The protective stop is meant to rest at the broker: it is not "an order that has not ended yet".
    open_orders = [order for order in book["orders"] if not order["ended"] and not order.get("protect")]
    stuck = [order for order in open_orders if time.time() - order["sent_at"] >= ATTENTION_AFTER_S]
    if any(not order["ended"] for order in orders) or (not orders and open_orders):
        state = "unknown" if stuck else "working"
    elif not orders or filled <= 0:
        state = "nothing"
    else:
        state = "done" if filled >= asked else "part"
    # Why an order ended with nothing, when the order service said why (refused, never reached the broker).
    note = note or "; ".join(order["note"] for order in orders if order.get("note"))
    resting = resting_stops(book)
    return {"state": state, "filled": filled, "price": round(value / filled, 2) if filled else 0.0, "held": held,
            "working_entry": working_lots(book, "ENTRY"),
            "working_exit": working_lots(book, "EXIT") - sum(order["lots"] for order in resting),
            "protected": sum(order["lots"] for order in resting), "protection_lost": "protection_lost" in problems,
            "record_gap": "db_failed" in problems, "not_recorded": "failed" in problems, "note": note}


WATCH_KEY = "position_watch:{request_id}"     # read by the order service for the guard: keep the name in step
WATCH_KEPT_S = 7 * 24 * 60 * 60


def mark_watched(handle):
    """ Notes that this request's run looked at its position just now. A guard outside the run reads it: a position
    whose run has stopped looking has nobody watching it. Never breaks the caller. """
    try:
        handle["state_cursor"].set(WATCH_KEY.format(request_id=handle["request_id"]), time.time(), ex=WATCH_KEPT_S)
    except Exception as e:
        print(f"Exception in mark_watched : {e}")


def locked(handle, action):
    """ Runs action(token) holding the request's lock; "busy" when the lock cannot be had. """
    mark_watched(handle)
    token = acquire_exit_mutex(handle["state_cursor"], handle["request_id"])
    if token is None:
        return {"state": "busy", "filled": 0, "price": 0.0, "held": None, "working_entry": None, "working_exit": None,
                "protected": None, "protection_lost": False,
                "record_gap": False, "not_recorded": False, "note": "another actor holds this request's lock"}
    try:
        return action(token)
    finally:
        release_exit_mutex(handle["state_cursor"], handle["request_id"], token)


def open_position(handle, lots, order_type="MARKET", price=None, wait_s=REQUEST_WAIT_S):
    """ Sends the entry order of a position that holds nothing and has no entry in flight. """
    def action(token):
        book = read_book(handle)
        problems = bring_up_to_date(handle, book)
        held, _ = held_lots(handle)
        if held > 0 or working_lots(book, "ENTRY") > 0:
            return answer(handle, book, problems=problems, note="the position is already open or its entry is still working")
        order = send_order(handle, book, "ENTRY", None, lots, order_type, price)
        wait_for(handle, book, [order], wait_s, token)
        problems += bring_up_to_date(handle, book)
        return answer(handle, book, [order], problems)
    return locked(handle, action)


def exit_lots(handle, book, lots, reason, wait_s, token, problems):
    """ Exits up to `lots`, never more than is free; after a part fill the rest is sent again. """
    orders = []
    left = lots
    asked = None
    for attempt in range(EXIT_ORDERS_PER_REQUEST):
        held, _ = held_lots(handle)
        left = min(left, held - working_lots(book, "EXIT"))
        if left <= 0:
            break
        asked = left if asked is None else asked
        order = send_order(handle, book, "EXIT", reason, left, "MARKET", None)
        orders.append(order)
        wait_for(handle, book, [order], wait_s, token)
        problems += bring_up_to_date(handle, book)
        if not order["ended"] or order["filled"] <= 0 or not order["booked"]:
            break
        left -= order["filled"]
    note = "" if orders else "nothing is free to exit: nothing is held, or exits already sent cover it"
    return answer(handle, book, orders, problems, note, asked)


def resting_stops(book):
    return [order for order in book["orders"] if order.get("protect") and not order["ended"]]


def reduce_position(handle, lots, reason, wait_s=REQUEST_WAIT_S):
    """ Exits `lots` under `reason` (the exit_type of the line), or as many of them as are free. A protective stop is
    taken off first (it covers the lots to be exited) and put back, at the same prices, for what is still held. """
    def action(token):
        book = read_book(handle)
        problems = bring_up_to_date(handle, book)
        stops = resting_stops(book)
        if stops:
            cancel_open_orders(handle, book, ("EXIT",), wait_s, token, only=stops)
            problems += bring_up_to_date(handle, book)
        result = exit_lots(handle, book, lots, reason, wait_s, token, problems)
        if stops:
            place_stop(handle, book, stops[-1]["reason"], stops[-1]["trigger"], stops[-1]["limit"], wait_s, token)
            result = dict(answer(handle, book, problems=bring_up_to_date(handle, book)),
                          **{key: result[key] for key in ("state", "filled", "price", "note", "record_gap", "not_recorded")})
        return result
    return locked(handle, action)


def cancel_open_orders(handle, book, side, wait_s, token, only=None):
    orders = [order for order in book["orders"] if not order["ended"] and order["side"] in side and (only is None or order in only)]
    for order in orders:
        order["cancel_asked"] = True
        if order["order_id"]:
            tell(handle, "cancel_sent", key=order["key"], order_id=order["order_id"])
            live.cancel_live_order(handle["credential_id"], order["order_id"], **owner(handle))
    if orders:
        wait_for(handle, book, orders, wait_s, token)


def place_stop(handle, book, reason, trigger_price, limit_price, wait_s, token):
    """ Sends the protective stop for every held lot that no exit order covers yet. Returns the order, or None when there
    is nothing to protect. """
    held, _ = held_lots(handle)
    free = held - working_lots(book, "EXIT")
    if free <= 0:
        return None
    order = send_order(handle, book, "EXIT", reason, free, "STOPLOSS", limit_price, trigger=trigger_price, protect=True)
    # A stop the broker takes rests there; one it refuses ends at once. A short look is enough to tell the two apart.
    wait_for(handle, book, [order], min(wait_s, STOP_LOOK_S), token)
    return order


def protect_position(handle, reason, trigger_price, limit_price, wait_s=REQUEST_WAIT_S):
    """ Keeps one protective stop resting at the broker for all that is held: a stop-limit exit, for the case that this
    run, its server or the price feed stops. `reason` is the exit_type its fill is recorded under; give the strategy's
    own stop-loss name, so the trade is closed by it like any other stop.

    It is a second line, not the stop itself. The exchange allows only stop-LIMIT orders on options: in a fast move the
    price can pass the limit and the stop does not fill, and a stop whose limit is outside the exchange's allowed range
    at the moment it triggers is thrown out. The answer's protection_lost says when the stop has gone without filling.

    Called again with the same prices it does nothing. With other prices, or after the position has changed size, the
    old stop is taken off and a new one placed. reduce_position and close_position take the stop off before they exit.
    For a LONG the trigger must not be below the limit; for a SHORT it must not be above it. """
    if not trigger_price or not limit_price or trigger_price <= 0 or limit_price <= 0:
        raise ValueError(f"a protective stop needs a trigger and a limit price above zero, got {trigger_price!r} and {limit_price!r}")
    if (handle["position_type"] == "LONG" and trigger_price < limit_price) or (handle["position_type"] == "SHORT" and trigger_price > limit_price):
        raise ValueError(f"for a {handle['position_type']} position the limit ({limit_price}) is on the wrong side of the trigger ({trigger_price})")

    def action(token):
        book = read_book(handle)
        problems = bring_up_to_date(handle, book)
        held, _ = held_lots(handle)
        stops = resting_stops(book)
        fits = (len(stops) == 1 and stops[0]["trigger"] == trigger_price and stops[0]["limit"] == limit_price
                and stops[0]["lots"] == held - (working_lots(book, "EXIT") - stops[0]["lots"]))
        if fits:
            return answer(handle, book, problems=problems)
        if stops:
            cancel_open_orders(handle, book, ("EXIT",), wait_s, token, only=stops)
            problems += bring_up_to_date(handle, book)
        order = place_stop(handle, book, reason, trigger_price, limit_price, wait_s, token)
        problems += bring_up_to_date(handle, book)
        result = answer(handle, book, problems=problems)
        if order is None:
            result["note"] = "nothing to protect: nothing is held, or exits already sent cover it"
        elif order["ended"] and order["filled"] <= 0:
            result["note"] = order.get("note") or "the broker did not take the protective stop"
        return result
    return locked(handle, action)


def close_position(handle, reason, wait_s=REQUEST_WAIT_S):
    """ Exits all that is held: cancels the exits still working, waits for them to end, then exits what is left. Lots of an
    exit whose result is still not known are not exited again. """
    def action(token):
        book = read_book(handle)
        problems = bring_up_to_date(handle, book)
        cancel_open_orders(handle, book, ("EXIT",), wait_s, token)
        problems += bring_up_to_date(handle, book)
        held, _ = held_lots(handle)
        return exit_lots(handle, book, held, reason, wait_s, token, problems)
    return locked(handle, action)


def cancel_working(handle, wait_s=REQUEST_WAIT_S):
    """ Cancels what is still open of every order of the position, and books what they filled. """
    def action(token):
        book = read_book(handle)
        cancel_open_orders(handle, book, ("ENTRY", "EXIT"), wait_s, token)
        return answer(handle, book, problems=bring_up_to_date(handle, book))
    return locked(handle, action)


def sync_position(handle):
    """ Brings the book up to date and books what has filled. Sends no order, but takes off a protective stop that covers
    more than is held (someone else closed or trimmed the position): left resting, it would open a position the other
    way when it triggers. Cheap when nothing is in flight. """
    if not read_book(handle)["orders"]:
        mark_watched(handle)
        return answer(handle, {"orders": []})

    def action(token):
        book = read_book(handle)
        problems = bring_up_to_date(handle, book)
        stops = resting_stops(book)
        held, _ = held_lots(handle)
        if stops and sum(order["lots"] for order in stops) > held:
            tell(handle, "stop_covers_more_than_held", held=held, covered=sum(order["lots"] for order in stops))
            cancel_open_orders(handle, book, ("EXIT",), REQUEST_WAIT_S, token, only=stops)
            problems += bring_up_to_date(handle, book)
        return answer(handle, book, problems=problems)
    return locked(handle, action)
