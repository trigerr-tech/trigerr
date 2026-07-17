from trigerr.orders import add_order_to_redis, fetch_orders_list
from trigerr.utils import send_order_alert
from trigerr.config import config
import requests
from urllib.parse import urljoin
import datetime
import json
import time
orders_url = config.get("orders_url")


def place_lt_order(symbol, exchange="NSE", quantity=1, transaction_type="BUY", order_type="MARKET", lot_size=1,
                   credential_id=None, trigger_price=None, order_price=None, validity="DAY", asset_type="EQUITY",
                   holding_type="DELIVERY", option_type=None, strike_price=None, underlying=None, expiry_date=None, max_qpo=None):
    """ Function to Place Live Trading Order """
    try:
        order_data_params = {"symbol": symbol,
                             "exchange": exchange,
                             "transaction_type": transaction_type,
                             "quantity": quantity * lot_size,
                             "asset_type": asset_type,
                             "validity": validity,
                             "order_type": order_type,
                             "trigger_price": trigger_price,
                             "price": order_price,
                             "option_type": option_type,
                             "strike_price": strike_price,
                             "underlying": underlying,
                             "expiry_date": expiry_date,
                             "holding_type": holding_type,
                             "lot_size": lot_size,
                             "max_qpo": max_qpo
                             }

        order_response = place_live_order(credential_id=credential_id, order_details=order_data_params)

        if order_response["status"] == "SUCCESS":
            return "success", order_response
        else:
            return "error", order_response

    except Exception as e:
        print(f"Exception in placing live trade : {e}")
        return "failed", None


def save_lt_order(app_db_cursor, redis_cursor, orders_list, symbol, quantity, quantity_left=0,
                  position_type="LONG", transaction_type="BUY", trade_action="ENTRY", order_type="MARKET",
                  exit_type=None, params=None, market_type="options", trigger_price=None, lot_size=25,
                  user_id=None, strategy_id=None, request_id=None, exchange="NSE", exchange_timestamp=None,
                  order_id=None, broker_response=None, sl_order_id=None, validity="DAY", market="IN", holding_type="INTRADAY",
                  asset_type="EQUITY", option_type=None, strike_price=None, underlying=None, expiry_date=None, max_qpo=None):
    """ Function to save order in Database """
    try:
        order_dict = {
            "market": market,
            "tradingsymbol": symbol,
            "exchange": exchange,
            "user_id": user_id,
            "strategy_id": strategy_id,
            "request_id": request_id,
            "quantity": quantity,
            "quantity_left": quantity_left,
            "position_type": position_type,
            "transaction_type": transaction_type,
            "trade_action": trade_action,
            "order_type": order_type,
            "asset_type": asset_type,
            "exit_type": exit_type,
            "lot_size": lot_size,
            "max_qpo": max_qpo,
            "exchange_timestamp": exchange_timestamp,
            "status": "COMPLETE",
            "trigger_price": trigger_price,
            "order_id": order_id,
            "validity": validity,
            "holding_type": holding_type,
            "market_type": market_type,
            "option_type": option_type,
            "strike_price": strike_price,
            "underlying": underlying,
            "expiry_date": expiry_date
        }

        if sl_order_id:
            order_dict["sl_order_id"] = sl_order_id

        order_dict["order_timestamp"] = exchange_timestamp
        order_dict["date"] = datetime.datetime.strptime(str(datetime.datetime.today().date()), '%Y-%m-%d')
        order_dict["day"] = order_dict["date"].strftime("%A")

        if params:
            order_dict.update(params)

        # Creating New Dict for saving data in to db
        lt_order_dict = {}
        for key in order_dict.keys():
            lt_order_dict[key] = order_dict[key]

        lt_order_dict["order_id"] = order_id
        lt_order_dict["broker_response"] = broker_response
        lt_order_dict["trade_action"] = lt_order_dict["trade_action"]

        # Saving Order Details to Database
        lt_order_id = app_db_cursor["lt_orders"].insert_one(lt_order_dict).inserted_id
        lt_order_dict["db_order_id"] = lt_order_id
        order_dict["db_order_id"] = lt_order_id

        # Converting Dict to String
        redis_dict = {k: str(v) if not isinstance(v, (int, float)) else v for k, v in order_dict.items()}

        # redis_dict["quantity_left"] = str(quantity_left)

        # Adding Order to Redis
        add_order_to_redis(redis_cursor=redis_cursor, request_id=str(request_id), order_dict=redis_dict, mode="lt")

        # Creating Alert Dict
        alert_dict = {"user_id": str(order_dict["user_id"]),
                      "strategy_id": str(order_dict["strategy_id"]),
                      "request_id": str(order_dict["request_id"]),
                      "mode": "lt",
                      "exit_type": exit_type,
                      "symbol": symbol,
                      "quantity": quantity,
                      "price": trigger_price,
                      "quantity_left": quantity_left,
                      "trade_action": trade_action,
                      "position_type": position_type,
                      "template_id": 0
                      }
        print(f"Alert Dict : {alert_dict}")
        send_order_alert(alert_dict)

        orders_list = fetch_orders_list(redis_cursor=redis_cursor, request_id=str(request_id))
        return "success", orders_list

    except Exception as e:
        print(f"Exception in Saving Order in DB : {e}")
        return "failed", orders_list


def save_lt_trade(app_db_cursor, redis_cursor, trade_dict):
    """Function to save order in Database"""
    try:
        app_db_cursor["lt_trades"].insert_one(trade_dict)
        request_id = trade_dict["request_id"]
        redis_cursor.rpush(str(request_id) + "_trades", json.dumps(trade_dict, default=str))
        redis_cursor.publish(str(request_id) + "_trades", json.dumps(trade_dict, default=str))
        redis_cursor.publish(f"{trade_dict['user_id']}_lt_trades", json.dumps(trade_dict, default=str))
    except Exception as e:
        print(f"Exception in saving LT trade in DB : {e}")
        pass


def place_live_order(credential_id, order_details):
    """Function to place live trade order via REST API"""
    try:
        print("Placing Live Trade Order")
        request_dict = {"credential_id": str(credential_id),
                        "order_params": order_details}
        print(f"request_dict : {request_dict}")

        response = requests.post(url=urljoin(orders_url, "place_order"), json=request_dict)
        print("******** Order Placement Response *********")
        print(response.json())
        return response.json()
    except Exception as e:
        print(f"Exception in placing live trade order : {e}")
        return None


def modify_live_order(credential_id, order_details):
    """Function to Modify Live Order"""
    try:
        print("* Modifying Live Order")
        request_dict = {"credential_id": str(credential_id),
                        "order_params": order_details}
        print(f"request_dict : {request_dict}")

        response = requests.post(url=urljoin(orders_url, "modify_order"), json=request_dict)
        print("******** Order Placement Response *********")
        print(response.json())
        return response.json()
    except Exception as e:
        print(f"Exception in Modify Live Order : {e}")
        pass


def check_order_status(credential_id, order_id, exchange):
    """Function to fetch current order status"""
    try:
        print("Fetching Order Status")
        request_dict = {
            "credential_id": str(credential_id),
            "order_params": {
                'order_id': order_id,
                "exchange": exchange
            }
        }
        # last_order = requests.post(url=orders_url+"get_order_by_id", params={"credential_id": credential_id, 'order_details': json.dumps(get_order_params)}).json()
        last_order = requests.post(url=urljoin(orders_url, "check_order_status"), json=request_dict).json()
        print(f"order_status_response : {last_order}")

        if last_order["status"] == "COMPLETED":
            last_order["timestamp"] = datetime.datetime.strptime(str(last_order["timestamp"]), '%Y-%m-%d %H:%M:%S')
            return "success", last_order

        elif last_order["status"] == "CANCELLED" or last_order["status"] == "REJECTED":
            return "cancelled", None
        else:
            return "error", None
    except Exception as e:
        print(f"Exception in Check Order Status Function : {e}")
        return "failed", None


def poll_order_status(credential_id, order_id, exchange, max_wait_seconds=1800, sleep_interval=1):
    """ Function to poll order status until terminal state is reached """
    order_response = None
    try:
        print(f"Polling Order Status for order_id: {order_id}")
        request_dict = {
            "credential_id": str(credential_id),
            "order_params": {'order_id': order_id, "exchange": exchange}
        }
        start_time = time.time()
        retry_count = 0

        while time.time() - start_time < max_wait_seconds:  # Poll indefinitely until terminal state
            order_response = requests.post(url=urljoin(orders_url, "check_order_status"), json=request_dict).json()

            current_status = order_response.get("status")

            print(f"Poll #{retry_count} | Status: {current_status} Filled: {order_response.get('filled_quantity', 0)}/{order_response.get('order_quantity', 0)}")

            # Check for terminal states - stop polling
            if current_status == "COMPLETED":
                print(f"Order COMPLETED - Filled: {order_response.get('filled_quantity')} | Avg Price: {order_response.get('average_price')}")
                order_response["timestamp"] = datetime.datetime.strptime(str(order_response["timestamp"]), '%Y-%m-%d %H:%M:%S')
                return "success", order_response

            elif current_status == "REJECTED":
                print(f"Order REJECTED: {order_response.get('message')}")
                order_response["timestamp"] = datetime.datetime.strptime(str(order_response["timestamp"]), '%Y-%m-%d %H:%M:%S')
                return "failed", order_response

            elif current_status == "CANCELLED":
                print(f"Order CANCELLED: {order_response.get('message')}")
                order_response["timestamp"] = datetime.datetime.strptime(str(order_response["timestamp"]), '%Y-%m-%d %H:%M:%S')
                return "failed", order_response

            elif current_status == "ERROR":
                print(f"Order ERROR: {order_response.get('message')}")
                order_response["timestamp"] = datetime.datetime.strptime(str(order_response["timestamp"]), '%Y-%m-%d %H:%M:%S')
                return "failed", order_response

            elif current_status == "OPEN":
                # Still pending - continue polling
                retry_count += 1
                time.sleep(sleep_interval)
                continue

            else:
                print(f"Unknown order status: {current_status}")
                return "failed", order_response
            
        print(f"Polling timeout reached for order_id: {order_id}")
        return "timeout", order_response

    except Exception as e:
        print(f"Exception in Poll Order Status Function: {e}")
        return "failed", order_response
