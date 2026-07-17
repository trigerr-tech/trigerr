from trigerr.config import config
import json
import requests
from urllib.parse import urljoin

api_key = config.get("api_key")
data_url = config.get("data_url")


def fetch_eod_candles(symbol, start_date, end_date, exchange="XNSE"):
    """ Function to fetch End of Day Candles for symbol """
    try:
        headers = {"x-api-key": api_key, "content-type": "application/json"}
        request_data = {"symbol": symbol, "exchange": exchange, "from_date": str(start_date), "to_date": str(end_date)}
        request_url = urljoin(data_url, "fetch-eod-data")
        eod_data = requests.post(url=request_url, headers=headers, json=request_data)
        return eod_data.json()
    except Exception as e:
        print(f"Exception in fetching eod candles : {e}")
        return []


def fetch_index_candles(symbol, start_date, end_date, granularity=1, exchange="XNSE"):
    """ Function to fetch candles for the respective date """
    try:
        headers = {"x-api-key": api_key, "content-type": "application/json"}
        request_data = {"symbol": symbol, "exchange": exchange, "from_date": str(start_date), "to_date": str(end_date), "granularity": granularity}
        request_url = urljoin(data_url, "fetch-index-data")
        candles_data = requests.post(url=request_url, headers=headers, json=request_data)
        if candles_data.status_code == 200:
            return candles_data.json()
        else:
            return []
    except Exception as e:
        print(f"Exception in fetching index candles : {e}")
        return []


def fetch_futures_candle(underlying, start_date, end_date, granularity=1, exchange="XNSE"):
    """ Function to Fetch Futures Candle Data """
    try:
        headers = {"x-api-key": api_key, "content-type": "application/json"}
        request_data = {"underlying": underlying, "from_date": str(start_date),
                        "to_date": str(end_date), "granularity": granularity, "exchange": exchange}
        request_url = urljoin(data_url, "fetch-futures-data")
        candles_data = requests.post(url=request_url, headers=headers, json=request_data)
        return candles_data.json()

    except Exception as e:
        print(f"Exception in fetching options candle by date : {e}")
        return []


def fetch_option_candles(underlying, start_date, end_date, option_type, strike_price, expiry="current", granularity=1,
                         timestamp=None, exchange="XNSE"):
    """ Function to Fetch Options Trade Data """
    try:
        headers = {"x-api-key": api_key, "content-type": "application/json"}
        request_data = {"underlying": underlying, "from_date": str(start_date),
                        "to_date": str(end_date),  "option_type": option_type, "strike_price": strike_price,
                        "expiry": expiry, "granularity": int(granularity),
                        "timestamp": str(timestamp) if timestamp else None,
                        "exchange": exchange}
        request_url = urljoin(data_url, "fetch-options-data")
        candles_data = requests.post(url=request_url, headers=headers, json=request_data)
        return candles_data.json()
    except Exception as e:
        print(f"Exception in fetching options candle : {e}")
        return []


def fetch_option_candles_by_symbol(underlying, symbol, start_date, end_date, granularity=1, timestamp=None, exchange="XNSE"):
    """ Function to Fetch Options Trade Data """
    try:
        headers = {"x-api-key": api_key, "content-type": "application/json"}
        request_data = {"underlying": underlying, "symbol": symbol, "from_date": str(start_date),
                        "to_date": str(end_date), "granularity": granularity,
                        "timestamp": str(timestamp) if timestamp else None,
                        "exchange": exchange}
        request_url = urljoin(data_url, "fetch-options-data-by-symbol")
        candles_data = requests.post(url=request_url, headers=headers, json=request_data)
        return candles_data.json()

    except Exception as e:
        print(f"Exception in fetching options candle : {e}")
        return []


def fetch_option_candles_by_date(underlying, start_date, end_date, granularity=1, exchange="XNSE"):
    """ Function to Fetch Options Trade Data """
    try:
        headers = {"x-api-key": api_key, "content-type": "application/json"}
        request_data = {"underlying": underlying, "from_date": str(start_date),
                        "to_date": str(end_date), "granularity": granularity, "exchange": exchange}
        request_url = urljoin(data_url, "fetch-options-data-by-date")
        candles_data = requests.post(url=request_url, headers=headers, json=request_data)
        return candles_data.json()

    except Exception as e:
        print(f"Exception in fetching options candle by date : {e}")
        return []


def fetch_option_candle_by_timestamp(underlying, strike_price, option_type, timestamp, granularity=1, expiry="current", exchange="XNSE"):
    """ Function to Fetch Order Candle based on timestamp """
    try:
        headers = {"x-api-key": api_key, "content-type": "application/json"}
        request_data = {"underlying": underlying, "option_type": option_type,
                        "strike_price": strike_price, "timestamp": str(timestamp), "expiry": expiry, "granularity": granularity,
                        "exchange": exchange}
        request_url = urljoin(data_url, "fetch-option-data-by-timestamp")
        candles_data = requests.post(url=request_url, headers=headers, json=request_data)
        return candles_data.json()

    except Exception as e:
        print(f"Exception in fetching order candle : {e}")
        return []


if __name__ == '__main__':
    # data_url = "http://127.0.0.1:5001"
    candle = fetch_option_candle_by_timestamp(underlying="SENSEX",  strike_price=80200, option_type="CE", expiry="current",
                                              timestamp="2024-12-19 14:45:00")
    print(json.loads(candle))
