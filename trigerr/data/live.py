import json
import datetime


def fetch_current_day_open(redis_cursor, symbol):
    """ Function to Fetch Current Day Open """
    try:
        print("fetching current day open price")
        candles_list = redis_cursor.lrange(symbol, 0, 1)
        if candles_list:
            candles_dict = json.loads(candles_list[0])
            print(f"current day open : {candles_dict['open']}")
            return candles_dict["open"]
    except Exception as e:
        print(f"Exception in fetching current day open : {e}")
        return None


def fetch_live_option_candle(redis_cursor, symbol, strike_price, option_type):
    """Function to fetch recent option candle"""
    try:
        print(f"fetching live option candle")
        symbol_ = symbol.replace(" ", "_")
        key_name = f"{symbol_}_{str(int(strike_price))}_{option_type}"
        key_symbol = f"all_symbols:{key_name}"
        poc_result = redis_cursor.get(key_symbol)
        if not poc_result:
            return None
        option_candle = json.loads(poc_result)[key_name]
        print(f"option_candle : {option_candle}")

        option_candle["close"] = option_candle["last_price"] if option_candle.get("last_price") else option_candle["close"]
        option_candle["timestamp"] = datetime.datetime.strptime(str(option_candle["timestamp"]), '%Y-%m-%d %H:%M:%S')
        option_candle["date"] = datetime.datetime.strptime(str(option_candle["timestamp"].date()), '%Y-%m-%d')
        # option_candle["expiry"] = datetime.datetime.today().date().isoformat()
        print(f"live option_candle : {option_candle}")
        return option_candle
    except Exception as e:
        print(f"Exception Fetching Option Candle : {e}")
        return None


def fetch_live_option_candles(redis_cursor, symbol, strike_price, option_type):
    """ Function to fetch current-day option candles """
    try:
        print("fetchin day option candles")
        symbol_ = symbol.replace(" ", "_")
        key_name = f"{symbol_}_{str(int(strike_price))}_{option_type}"
        print(f"key_name : {key_name}")
        candles = redis_cursor.lrange(key_name, 0, -1)
        if candles:
            candles_list = [json.loads(i) for i in candles]
            print(f"total live options candles till now : {len(candles_list)}")
            return candles_list
        else:
            return None
    except Exception as e:
        print(f"Exception in fetching day option candles : {e}")
        return None


def fetch_live_candle(redis_cursor, symbol):
    """Function to fetch recent candle"""
    try:
        print(f"fetching live candle")
        key_symbol = f"all_symbols:{symbol}"
        underlying_dict = redis_cursor.get(key_symbol)
        live_candle = json.loads(underlying_dict)[symbol]
        print(f"live_candle : {live_candle}")

        live_candle["close"] = live_candle["last_price"] if live_candle.get("last_price") else live_candle["close"]
        live_candle["timestamp"] = datetime.datetime.strptime(str(live_candle["timestamp"]), '%Y-%m-%d %H:%M:%S')
        live_candle["date"] = datetime.datetime.strptime(str(live_candle["timestamp"].date()), '%Y-%m-%d')
        return live_candle
    except Exception as e:
        print(f"Exception Fetching Live Candle : {e}")
        return None


def fetch_recent_candle(redis_cursor, symbol):
    """ Function to fetch Recent Candle from Redis """
    try:
        print("Fetching Recent Candle")
        recent_candle = json.loads(redis_cursor.lindex(symbol, -1))
        return recent_candle
    except Exception as e:
        print(f"Exception in Fetching Recent Candle {e}")
        return None


def fetch_live_candles(redis_cursor, symbol):
    """ Function to fetch current-day option candles """
    try:
        candles = redis_cursor.lrange(symbol, 0, -1)
        if candles:
            candles_list = [json.loads(i) for i in candles]
            print(f"total live options candles till now : {len(candles_list)}")
            return candles_list
        else:
            return None
    except Exception as e:
        print(f"Exception in fetching live candles : {e}")
        return None


def fetch_live_future_candle(redis_cursor, symbol):
    """Function to fetch recent option candle"""
    try:
        print(f"fetching live option candle")
        symbol_ = symbol.replace(" ", "_")
        key_name = f"{symbol_}_FUTURES"
        key_symbol = f"all_symbols:{key_name}"
        poc_result = redis_cursor.get(key_symbol)
        if not poc_result:
            return None
        future_candle = json.loads(poc_result)
        future_candle["close"] = future_candle["last_price"] if future_candle.get("last_price") else future_candle["close"]
        future_candle["timestamp"] = datetime.datetime.strptime(str(future_candle["timestamp"]), '%Y-%m-%d %H:%M:%S')
        future_candle["date"] = datetime.datetime.strptime(str(future_candle["timestamp"].date()), '%Y-%m-%d')
        print(f"live future_candle : {future_candle}")
        return future_candle
    except Exception as e:
        print(f"Exception Fetching Future Candle : {e}")
        return None


def fetch_live_future_candles(redis_cursor, symbol):
    """ Function to fetch current-day futures candles """
    try:
        print("fetching day futures candles")
        symbol_ = symbol.replace(" ", "_")
        key_name = f"{symbol_}_FUTURES"
        print(f"key_name : {key_name}")
        candles = redis_cursor.lrange(key_name, 0, -1)
        if candles:
            candles_list = [json.loads(i) for i in candles]
            print(f"total live futures candles till now : {len(candles_list)}")
            return candles_list
        else:
            return None
    except Exception as e:
        print(f"Exception in fetching day futures candles : {e}")
        return None


def fetch_eod_candles_cache(redis_cursor, symbol):
    """ Function to fetch EOD Candles from Redis Cache """
    try:
        candles = redis_cursor.lrange(f"eod_{symbol}", 0, -1)
        if candles:
            candles_list = [json.loads(i) for i in candles]
            print(f"total live options candles till now : {len(candles_list)}")
            return candles_list
        else:
            return None
    except Exception as e:
        print(f"Exception in fetching cache EOD Candles : {e}")
        return None
