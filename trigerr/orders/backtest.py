import datetime

from trigerr.orders.orders_utils import fetch_orders_list, add_order_to_redis


def save_bt_report(app_db_cursor, report_dict):
    """Function to Save Backtest Report in Database"""
    try:
        app_db_cursor["bt_reports"].insert_one(report_dict)
        app_db_cursor["bt_request"].update_one({"_id": report_dict["request_id"]}, {"$set": {"status": "done"}})
    except Exception as e:
        print(f"Exception in saving BT Report : {e}")
        pass


def place_bt_order(order_candle, quantity, position_type="LONG", transaction_type="BUY", order_type="MARKET",
                   orders_list=list, option_type=None, strike_price=None, exit_type=None, quantity_left=0, params=None,
                   market_type="equity", trade_type=None, trade_action="ENTRY", trigger_price=None, lot_size=25,
                   user_id=None, strategy_id=None, request_id=None, exchange="NSE", option_params=None, market="IN",
                   holding_type="intraday"):
    """ Function to place Backtesting Order """
    try:

        print("************** Placing Backtesting Order **************")
        order_dict = {"exchange": exchange, "order_type": order_type, "position_type": position_type, "quantity": quantity,
                      "transaction_type": transaction_type, "exit_type": exit_type, "quantity_left": quantity_left,
                      "lot_size": lot_size, "trade_type": trade_type, "trade_action": trade_action,
                      "market": market, "holding_type": holding_type, "market_type": market_type}

        if trigger_price:
            order_dict["trigger_price"] = trigger_price
        else:
            order_dict["trigger_price"] = order_candle["close"]

        order_dict["order_timestamp"] = str(order_candle["timestamp"])
        order_dict["symbol"] = order_candle.get("symbol")
        order_dict["date"] = str(order_candle["date"])

        order_dict["expiry"] = order_candle.get("expiry", "")
        order_dict["option_type"] = option_type if option_type else ""
        order_dict["strike_price"] = strike_price if strike_price else ""

        order_dict["day"] = order_candle["date"].strftime("%A")

        if params:
            order_dict.update(params)

        if option_params:
            order_dict.update(option_params)

        print(f"***** bt_order : {order_dict}")
        orders_list.append(order_dict)

        return orders_list

    except Exception as e:
        print(f"Exception in placing backtesting order : {e}")
        pass


def place_bt_leg_order(redis_cursor, order_candle, quantity, quantity_left=0,
                       position_type="LONG", transaction_type="BUY", trade_action="ENTRY", exit_type=None,
                       order_type="MARKET", trigger_price=None, lot_size=15,
                       user_id=None, strategy_id=None, request_id=None, market="IN", params=None,
                       holding_type="intraday", market_type="equity", exchange="NSE",
                       data_key=None, venue=None, group_id=None, leg_key=None):
    """ One backtest order, in exactly place_vt_order's document shape, for the execution core.

    What differs from place_vt_order is deliberate: the order is stamped from the candle the
    strategy acted on (its date, time and weekday), not from the wall clock, because a backtest
    replays past days; it touches no database and sends no alert; and it raises on bad input
    or a missing result instead of swallowing it, because a silently missing order corrupts a whole
    backtest. The order
    goes to `redis_cursor` (a backtest's in-memory state cursor) through the same
    stringification and orders list the core reads back for vt and lt, so one core serves all
    three modes. Returns the request's orders list. """
    stamp = order_candle["timestamp"]
    if not isinstance(stamp, datetime.datetime):
        raise TypeError(f"a backtest order needs a datetime candle timestamp, got {stamp!r}")

    order_dict = {
        "user_id": user_id,
        "strategy_id": strategy_id,
        "request_id": request_id,
        "market": market,
        "exchange": exchange,
        "venue": venue,
        "holding_type": holding_type,
        "market_type": market_type,
        "date": datetime.datetime(stamp.year, stamp.month, stamp.day),
        "order_timestamp": stamp.replace(microsecond=0),
        "day": stamp.strftime("%A"),
        "symbol": order_candle.get("symbol", ""),
        "data_key": data_key,
        "group_id": group_id,
        "leg_key": leg_key,
        "quantity": quantity,
        "quantity_left": quantity_left,
        "position_type": position_type,
        "transaction_type": transaction_type,
        "trade_action": trade_action,
        "order_type": order_type,
        "exit_type": exit_type,
        "lot_size": lot_size,
        "trigger_price": trigger_price if trigger_price else order_candle["close"],
    }
    if params:
        order_dict.update(params)

    redis_dict = {k: str(v) if not isinstance(v, (int, float)) else v for k, v in order_dict.items()}
    add_order_to_redis(redis_cursor=redis_cursor, request_id=str(request_id), order_dict=redis_dict, mode="bt")
    orders_list = fetch_orders_list(redis_cursor=redis_cursor, request_id=str(request_id))
    if not orders_list:
        raise RuntimeError("backtest order was not stored on the state cursor")
    return orders_list
