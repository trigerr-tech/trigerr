""" Historical data fetching module for the Trigerr SDK.

Delegates historical market data requests to the standalone sysstra-data client
package, which speaks the `/market-data/*` contract served by sysstra-data-services.
This replaced a set of raw `requests.post` calls against the older
`/fetch-*` routes (sysstra-data-api); that migration kept no aliases, so the old
route names no longer resolve.

`config` is re-exported by the star-imports in trigerr/utils.py — it looks unused
here, but removing this import breaks `import trigerr.utils` with a NameError.
"""
from trigerr.config import config
from sysstra_data import SysstraData


def _get_client():
    # Historical fetches can span years and hit an uncached range on their first call (see
    # sysstra-data-services' EOD cold-cache-stampede incident, 2026-08-21) — the SDK's short
    # default is tuned for live, latency-sensitive calls, which don't go through this module.
    #
    # Both values are read here rather than snapshotted at import time, so a
    # set_api_key()/set_data_url() call made after this module is imported still applies.
    client = SysstraData(api_key=config.get("api_key"), timeout=300)
    data_url = config.get("data_url")
    if data_url:
        client.set_base_url(data_url)
    return client


def fetch_eod_candles(symbol, start_date, end_date, exchange="XNSE"):
    """ Function to fetch End of Day Candles for symbol """
    try:
        client = _get_client()
        return client.equities.eod(symbol=symbol, from_date=str(start_date), to_date=str(end_date),
                                   exchange=exchange)
    except Exception as e:
        print(f"Exception in fetching eod candles : {e}")
        return []


def fetch_index_candles(symbol, start_date, end_date, granularity=1, exchange="XNSE"):
    """ Function to fetch candles for the respective date """
    try:
        client = _get_client()
        return client.equities.candles(symbol=symbol, from_date=str(start_date), to_date=str(end_date),
                                       interval=granularity, exchange=exchange)
    except Exception as e:
        print(f"Exception in fetching index candles : {e}")
        return []


def fetch_pre_open_candles(symbol, start_date, end_date, granularity=1, exchange="XNSE"):
    """ Function to fetch pre-open session candles for the respective date range """
    try:
        client = _get_client()
        return client.equities.pre_open(symbol=symbol, from_date=str(start_date), to_date=str(end_date),
                                        interval=granularity, exchange=exchange)
    except Exception as e:
        print(f"Exception in fetching pre-open candles : {e}")
        return []


def fetch_futures_candle(underlying, start_date, end_date, granularity=1, exchange="XNSE", expiry="current"):
    """ Function to Fetch Futures Candle Data """
    try:
        client = _get_client()
        return client.futures.candles(underlying=underlying, from_date=str(start_date), to_date=str(end_date),
                                      interval=granularity, expiry=expiry, exchange=exchange)
    except Exception as e:
        print(f"Exception in fetching futures candle : {e}")
        return []


def fetch_option_candles(underlying, start_date, end_date, option_type, strike_price, expiry="current", granularity=1,
                         timestamp=None, exchange="XNSE"):
    """ Function to Fetch Options Trade Data """
    try:
        client = _get_client()
        return client.options.candles(underlying=underlying, from_date=str(start_date), to_date=str(end_date),
                                      option_type=option_type, strike=strike_price, expiry=expiry,
                                      interval=granularity, timestamp=str(timestamp) if timestamp else None,
                                      exchange=exchange)
    except Exception as e:
        print(f"Exception in fetching options candle : {e}")
        return []


# The three lookups below were served by sysstra-data-api's /fetch-options-data-by-symbol,
# /fetch-options-data-by-date and /fetch-option-data-by-timestamp. sysstra-data-services has
# no successor route for any of them, so they raise rather than 404 into a swallowed [].
# Nothing in project-trigerr calls these (verified 2026-09-07).

def fetch_option_candles_by_symbol(underlying, symbol, start_date, end_date, granularity=1, timestamp=None, exchange="XNSE"):
    raise NotImplementedError("sysstra-data-services has no options-by-symbol route")


def fetch_option_candles_by_date(underlying, start_date, end_date, granularity=1, exchange="XNSE"):
    raise NotImplementedError("sysstra-data-services has no options-by-date route")


def fetch_option_candle_by_timestamp(underlying, strike_price, option_type, timestamp, granularity=1, expiry="current", exchange="XNSE"):
    raise NotImplementedError("sysstra-data-services has no option-by-timestamp route")
