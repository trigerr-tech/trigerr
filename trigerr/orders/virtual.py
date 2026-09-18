from trigerr.orders.orders_utils import add_order_to_redis, fetch_orders_list
from trigerr.utils import send_order_alert
import datetime
import json


def place_vt_order(app_db_cursor, redis_cursor, order_candle, quantity, quantity_left=0,
                   position_type="LONG", transaction_type="BUY", trade_action="ENTRY", exit_type=None,
                   order_type="MARKET", trigger_price=None, lot_size=15,
                   user_id=None, strategy_id=None, request_id=None, market="IN", params=None,
                   holding_type="intraday", market_type="equity", exchange="NSE"):
    """ Function to Place Virtual Trading Order """
    try:
        order_dict = {
            "user_id": user_id,
            "strategy_id": strategy_id,
            "request_id": request_id,
            "market": market,
            "exchange": exchange,
            "holding_type": holding_type,
            "market_type": market_type,
            "date": datetime.datetime.strptime(str(datetime.datetime.today().date()), '%Y-%m-%d'),
            "order_timestamp": datetime.datetime.now().replace(microsecond=0),
            "day": order_candle["timestamp"].strftime("%A"),
            "tradingsymbol": order_candle.get("symbol", ""),
            "quantity": quantity,
            "quantity_left": quantity_left,
            "position_type": position_type,  # LONG or SHORT
            "transaction_type": transaction_type,  # BUY or SELL
            "trade_action": trade_action,  # EXIT or ENTRY
            "order_type": order_type,  # LIMIT, MARKET, SL
            "exit_type": exit_type,  # T1, SL, TSL, MARKETEXIT, MANUAL
            "lot_size": lot_size
        }

        if trigger_price:
            order_dict["trigger_price"] = trigger_price
        else:
            order_dict["trigger_price"] = order_candle["close"]

        if params:
            order_dict.update(params)

        # Saving Order Details to Database
        order_id = save_vt_order(app_db_cursor=app_db_cursor, order_dict=order_dict.copy())
        print(f"VT order id : {order_id}")

        order_dict["db_order_id"] = str(order_id)

        # Converting Order Dict to String
        redis_dict = {k: str(v) if not isinstance(v, (int, float)) else v for k, v in order_dict.items()}

        # Adding Order to Redis
        add_order_to_redis(redis_cursor=redis_cursor, request_id=str(request_id), order_dict=redis_dict, mode="vt")

        # Creating Alert Dict
        alert_dict = {
            "user_id": str(order_dict["user_id"]),
            "strategy_id": str(order_dict["strategy_id"]),
            "request_id": str(order_dict["request_id"]),
            "mode": "vt",
            "exit_type": exit_type,
            "symbol": order_candle["symbol"],
            "quantity": quantity,
            "price": order_dict["trigger_price"],
            "quantity_left": quantity_left,
            "trade_action": trade_action,
            "position_type": position_type,
            "template_id": 0
        }
        print(f"Alert Dict : {alert_dict}")
        # Sending Alert
        send_order_alert(alert_dict)

        orders_list = fetch_orders_list(redis_cursor=redis_cursor, request_id=str(request_id))

        return orders_list
    except Exception as e:
        print(f"Exception in placing virtual trade : {e}")
        pass


def save_vt_order(app_db_cursor, order_dict):
    """Function to save order in Database"""
    try:
        order_id = app_db_cursor["vt_orders"].insert_one(order_dict).inserted_id
        return order_id
    except Exception as e:
        print(f"Exception in saving VT order in DB : {e}")
        pass


def save_vt_trade(app_db_cursor, redis_cursor, trade_dict):
    """Function to save order in Database"""
    try:
        app_db_cursor["vt_trades"].insert_one(trade_dict)
        request_id = trade_dict["request_id"]
        trades_key = str(request_id) + "_trades"
        # 20h, matching common_runner.py's LOCK_TTL_S: this list is scoped to
        # the same request/session, and nothing else expires it otherwise.
        if redis_cursor.rpush(trades_key, json.dumps(trade_dict, default=str)) == 1:
            redis_cursor.expire(trades_key, 20 * 60 * 60)
        redis_cursor.publish(trades_key, json.dumps(trade_dict, default=str))
        redis_cursor.publish(f"{trade_dict['user_id']}_vt_trades", json.dumps(trade_dict, default=str))
    except Exception as e:
        print(f"Exception in saving VT trade in DB : {e}")
        pass
