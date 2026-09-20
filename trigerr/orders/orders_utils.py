from trigerr.utils import calculate_brokerage
from trigerr import config
import json
import datetime
from bson import ObjectId
import requests

orders_url = config.get('orders_url')


def add_order_to_redis(redis_cursor, request_id, order_dict, mode):
    """Function to add order to redis"""
    try:
        orders_key = str(request_id) + "_orders"
        # 20h, matching common_runner.py's LOCK_TTL_S: this list is scoped to
        # the same request/session, and nothing else expires it otherwise.
        if redis_cursor.rpush(orders_key, json.dumps(order_dict, default=str)) == 1:
            redis_cursor.expire(orders_key, 20 * 60 * 60)
        redis_cursor.publish(orders_key, json.dumps(order_dict, default=str))
        redis_cursor.publish(f'{str(order_dict["user_id"])}_{mode}_orders', json.dumps(order_dict, default=str))
        # redis_cursor.publish(str(order_dict["user_id"]) + "_{}".format(mode) + "_orders", json.dumps(order_dict, default=str))
    except Exception as e:
        print(f"Exception in adding order in redis : {e}")
        pass


def fetch_orders_list(redis_cursor, request_id):
    """ Function to fetch an orders list for request_id """
    try:
        orders_list_json = redis_cursor.lrange(str(request_id)+"_orders", 0, -1)
        orders_list = [json.loads(i) for i in orders_list_json]
        return orders_list
    except Exception as e:
        print(f"Exception in fetching orders list : {e}")
        pass


def fetch_orders_mgdb(db_cursor, request_id, mode="vt"):
    """ Function to Fetch Orders list for Request ID """
    try:
        print()
        if mode == "vt":
            orders_col = "vt_orders"
        elif mode == "lt":
            orders_col = "lt_orders"
        else:
            orders_col = "bt_orders"
        orders_list = db_cursor[orders_col].find({"request_id": ObjectId(request_id)})
        if orders_list:
            return list(orders_list)
        else:
            return None
    except Exception as e:
        print(f"Exception in fetching orders list : {e}")
        pass


def fetch_last_order(redis_cursor, request_id):
    """Function to fetch last order from redis database"""
    try:
        last_order = json.loads(redis_cursor.lindex(str(request_id) + "_orders", -1))
        return last_order
    except Exception as e:
        print(f"Exception in fetching last order : {e}")
        pass


def check_open_orders(orders_list):
    """ Function to open orders available """
    try:
        if orders_list:
            quantity_dict = {}
            for order in orders_list:
                trade_symbol = order["tradingsymbol"]
                quantity_dict[trade_symbol] = {}
                quantity_dict[trade_symbol]["buy_quantity"] = 0
                quantity_dict[trade_symbol]["sell_quantity"] = 0
                quantity_dict[trade_symbol]["quantity"] = 0
                quantity_dict[trade_symbol]["exit_levels"] = []
                quantity_dict[trade_symbol]["order_timestamp"] = ""
                quantity_dict[trade_symbol]["quantity_left"] = 0

            for order in orders_list:
                trade_symbol = order["tradingsymbol"]
                if order["trade_action"] == "ENTRY":
                    # Adding Must Have Fields
                    quantity_dict[trade_symbol]["underlying"] = order.get("underlying", "")
                    quantity_dict[trade_symbol]["buy_quantity"] = order["quantity"]
                    quantity_dict[trade_symbol]["quantity"] = order["quantity"]
                    quantity_dict[trade_symbol]["quantity_left"] = order["quantity_left"]
                    quantity_dict[trade_symbol]["trigger_price"] = order["trigger_price"]
                    quantity_dict[trade_symbol]["order_timestamp"] = datetime.datetime.strptime(str(order["order_timestamp"]), '%Y-%m-%d %H:%M:%S')

                    # Adding Good to Have Fields
                    quantity_dict[trade_symbol]["position_type"] = order.get("position_type", "")
                    quantity_dict[trade_symbol]["spot_price"] = order.get("spot_price")
                    quantity_dict[trade_symbol]["strike_price"] = order.get("strike_price", "")
                    quantity_dict[trade_symbol]["option_type"] = order.get("option_type", "")
                    quantity_dict[trade_symbol]["bnf_price"] = order.get("bnf_price")
                    quantity_dict[trade_symbol]["expiry"] = order.get("expiry", "")
                    quantity_dict[trade_symbol]["sl_order_id"] = order.get("sl_order_id", "")
                    quantity_dict[trade_symbol]["db_order_id"] = order.get("db_order_id", "")
                    quantity_dict[trade_symbol]["trailing_sl"] = order.get("trailing_sl", "")
                    quantity_dict[trade_symbol]["t1_price"] = order.get("t1_price", "")
                    quantity_dict[trade_symbol]["sl_price"] = order.get("sl_price", "")
                    quantity_dict[trade_symbol]["t2_price"] = order.get("t2_price", "")
                    quantity_dict[trade_symbol]["t3_price"] = order.get("t3_price", "")
                    quantity_dict[trade_symbol]["liquidation_price"] = order.get("liquidation_price", "")
                    quantity_dict[trade_symbol]["hka_option_order_price"] = order.get("hka_option_order_price", "")
                    quantity_dict[trade_symbol]["option_order_price"] = order.get("option_order_price", "")
                    quantity_dict[trade_symbol]["spot_t1_price"] = order.get("spot_t1_price", "")
                    quantity_dict[trade_symbol]["spot_t2_price"] = order.get("spot_t2_price", "")
                    quantity_dict[trade_symbol]["spot_t3_price"] = order.get("spot_t3_price", "")
                    quantity_dict[trade_symbol]["spot_sl_price"] = order.get("spot_sl_price", "")
                    quantity_dict[trade_symbol]["spot_trailing_sl"] = order.get("spot_trailing_sl", "")
                    quantity_dict[trade_symbol]["option_t1_price"] = order.get("option_t1_price", "")
                    quantity_dict[trade_symbol]["option_sl_price"] = order.get("option_sl_price", "")
                    quantity_dict[trade_symbol]["option_trailing_sl"] = order.get("option_trailing_sl", "")

                elif order["trade_action"] == "EXIT":
                    quantity_dict[trade_symbol]["sell_quantity"] += order["quantity"]
                    quantity_dict[trade_symbol]["quantity_left"] = order["quantity_left"]
                    quantity_dict[trade_symbol]["exit_levels"].append(order["exit_type"])

            final_out = {}
            for entries in quantity_dict:
                if quantity_dict[entries]["quantity_left"] > 0:
                    final_out[entries] = quantity_dict[entries]
            return final_out

        else:
            return {}
    except Exception as e:
        print(f"Exception in checking open orders : {e}")
        return {}


def convert_to_trades(orders_list, market_type, order_exit_levels, mode, broker, holding_type="intraday"):
    """Function to convert Orders to Trades """
    try:
        trade_dict = {}
        trades_array = []
        for order in orders_list:
            if order["trade_action"] == "ENTRY":
                trade_dict["date"] = order["date"]
                trade_dict["stock"] = order["tradingsymbol"]
                trade_dict["exchange"] = order.get("exchange", "NSE")
                trade_dict["market"] = order.get("market", "IN")
                trade_dict["lot_size"] = order["lot_size"]
                trade_dict["position_type"] = order.get("position_type", "LONG")
                trade_dict["bnf_price"] = order.get("bnf_price", "")
                trade_dict["spot_price"] = order.get("spot_price", "")
                trade_dict["bar_color"] = order.get("bar_color", "")
                trade_dict["entry_time"] = order["order_timestamp"]
                trade_dict["entry_price"] = order["trigger_price"]
                trade_dict["quantity"] = order["quantity"]
                trade_dict["investment"] = order["investment"]
                trade_dict["day"] = order.get("day", "")
                trade_dict["expiry"] = order.get("expiry", "")
                trade_dict["pnl"] = 0
                trade_dict["points"] = 0
                trade_dict["exit_time"] = None
                trade_dict["exit_price"] = None
                trade_dict["exit_type"] = ""
                trade_dict["brokerage"] = 0
                trade_dict["net_pnl"] = 0
                trade_dict["option_type"] = order.get("option_type", "")
                trade_dict["strike_price"] = order.get("strike_price", "")
                trade_dict["expiry"] = order.get("expiry", "")
                trade_dict["liquidation_price"] = order.get("liquidation_price", "")

                if mode == "lt" or mode == "vt":
                    trade_dict["date"] = datetime.datetime.strptime(str(datetime.datetime.today().date()), '%Y-%m-%d')
                    trade_dict["user_id"] = ObjectId(order["user_id"])
                    trade_dict["strategy_id"] = ObjectId(order["strategy_id"])
                    trade_dict["request_id"] = ObjectId(order["request_id"])

                # Adding Indicators Values in the Calculated Trade Dict
                for input_key in order.keys():
                    if input_key.startswith("underlying_"):
                        trade_dict[input_key] = order[input_key]

                for input_key in order.keys():
                    if input_key.startswith("options_"):
                        trade_dict[input_key] = order[input_key]

                for input_key in order.keys():
                    if input_key.startswith("futures_"):
                        trade_dict[input_key] = order[input_key]

            else:
                # A crypto contract is a fraction of a coin (0.001 BTC), so whole-unit rounding would discard
                # most of the P&L; every other market keeps the whole-number rounding it was tested with.
                pnl_decimals = 2 if trade_dict.get("market") == "CRYPTO" else None
                if market_type == "spot" or market_type == "futures":
                    if order["position_type"] == "SHORT":
                        points = trade_dict["entry_price"] - order["trigger_price"]
                        trade_dict["points"] += round(points, pnl_decimals)
                        trade_dict["pnl"] += round(order["quantity"] * points, pnl_decimals)
                    else:
                        points = order["trigger_price"] - trade_dict["entry_price"]
                        trade_dict["points"] += round(points, pnl_decimals)
                        trade_dict["pnl"] += round(order["quantity"] * points, pnl_decimals)
                else:
                    if order["position_type"] == "SHORT":
                        points = trade_dict["entry_price"] - order["trigger_price"]
                    else:
                        points = order["trigger_price"] - trade_dict["entry_price"]
                    trade_dict["points"] += round(points, pnl_decimals)
                    trade_dict["pnl"] += round(order["quantity"] * points * trade_dict["lot_size"], pnl_decimals)

                if trade_dict["exit_type"]:
                    trade_dict["exit_type"] += "|" + order["exit_type"]
                else:
                    trade_dict["exit_type"] = order["exit_type"]

                if order["exit_type"] in order_exit_levels:
                    trade_dict["exit_time"] = order["order_timestamp"]
                    trade_dict["exit_price"] = order["trigger_price"]
                    tmp_market_type = "equity" if market_type == "spot" else market_type

                    # Exit-side details the strategy priced the fill with; a broker charging on the underlying
                    # (Delta) needs the spot at each fill rather than the premium.
                    for exit_key in ("exit_reason", "exit_spot_price"):
                        if order.get(exit_key) is not None:
                            trade_dict[exit_key] = order[exit_key]

                    brokerage, net_pnl = calculate_brokerage(buy_price=trade_dict["entry_price"], sell_price=trade_dict["exit_price"],
                                                             quantity=order["quantity"] * trade_dict["lot_size"], broker=broker, market_type=tmp_market_type,
                                                             lot_size=trade_dict["lot_size"], order_type=order["order_type"], position_type=order["position_type"],
                                                             holding_type=holding_type, market=trade_dict["market"], exchange=trade_dict["exchange"], no_of_orders=2,
                                                             spot_price=trade_dict.get("spot_price") or None, exit_spot_price=order.get("exit_spot_price") or None,
                                                             underlying=trade_dict.get("stock")
                                                             )
                    trade_dict["brokerage"] += brokerage

                    if order["exit_type"] == "LSL":
                        trade_dict["net_pnl"] -= trade_dict["investment"] + brokerage
                    else:
                        trade_dict["net_pnl"] += net_pnl

                    pnl_percent = round((trade_dict["net_pnl"] / trade_dict["investment"]) * 100, 2)
                    trade_dict["pnl_percent"] = pnl_percent
                    trades_array.append(trade_dict)

                    # Emptying Trade Dict for next trade
                    trade_dict = {}
                else:
                    print(f"trade_dict : {trade_dict}")
                    tmp_market_type = "equity" if market_type == "spot" else market_type
                    brokerage, net_pnl = calculate_brokerage(buy_price=trade_dict["entry_price"], sell_price=order["trigger_price"],
                                                             quantity=order["quantity"] * trade_dict["lot_size"], broker=broker, market_type=tmp_market_type,
                                                             lot_size=trade_dict["lot_size"], order_type=order["order_type"], position_type=order["position_type"],
                                                             holding_type=holding_type, market=trade_dict["market"], exchange=trade_dict["exchange"], no_of_orders=2,
                                                             spot_price=trade_dict.get("spot_price") or None, exit_spot_price=order.get("exit_spot_price") or None,
                                                             underlying=trade_dict.get("stock"))
                    trade_dict["brokerage"] += brokerage
                    trade_dict["net_pnl"] += net_pnl
        return trades_array
    except Exception as e:
        print(f"Exception in converting orders to trades : {e}")
        pass


def check_existing_order(symbol, exit_type, orders_list, entry_time):
    """ Function to check existing order on defined symbol """
    try:
        for order in orders_list:
            try:
                ot_time = datetime.datetime.strptime(str(order["order_timestamp"]), '%Y-%m-%d %H:%M')
            except Exception as b:
                ot_time = datetime.datetime.strptime(str(order["order_timestamp"]), '%Y-%m-%d %H:%M:%S')

            try:
                et_time = datetime.datetime.strptime(str(entry_time), '%Y-%m-%d %H:%M')
            except Exception as b:
                et_time = datetime.datetime.strptime(str(entry_time), '%Y-%m-%d %H:%M:%S')

            if order["tradingsymbol"] == symbol and order["exit_type"] == exit_type and ot_time >= et_time:
                return True
        return False
    except Exception as e:
        print(f"Exception in checking existing order : {e}")
        pass


# def check_order_status(credential_id, order_id, exchange):
#     """Function to fetch current order status"""
#     try:
#         print("Fetching Order Status")
#         get_order_params = {'order_id': order_id, "exchange": exchange}
#         last_order = requests.post(url=orders_url+"get_order_by_id", params={"credential_id": credential_id, 'order_details': json.dumps(get_order_params)}).json()
#         print(f"order_status_response : {last_order}")
#         if last_order["status"] == "COMPLETE":
#             last_order["exchange_timestamp"] = datetime.datetime.strptime(str(last_order["exchange_timestamp"]), '%Y-%m-%d %H:%M:%S')
#             return "success", last_order
#
#         elif last_order["status"] == "CANCELLED":
#             return "cancelled", None
#         else:
#             return "failed", None
#     except Exception as e:
#         print(f"Exception in Check Order Status Function : {e}")
#         return "failed", None
