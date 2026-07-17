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
        order_dict["tradingsymbol"] = order_candle.get("symbol")
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
