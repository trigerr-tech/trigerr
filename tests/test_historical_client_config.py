""" historical.py must read api_key/data_url when a fetch runs, not when it is imported.

The previous implementation snapshotted both into module globals at import time, so a
consumer that called set_api_key()/set_data_url() after the first import silently sent
every request with api_key=None to data_url=None — which urljoin turned into an
exception, swallowed by the bare except into an empty candle list.
"""
from trigerr.config import config
from trigerr.data import historical


def test_client_picks_up_config_set_after_import():
    saved = dict(config)
    try:
        config["api_key"] = "set-after-import"
        config["data_url"] = "https://data.example.invalid/"
        client = historical._get_client()
        assert client._http.api_key == "set-after-import"
        assert client._http.base_url.startswith("https://data.example.invalid")
    finally:
        config.clear()
        config.update(saved)


def test_routes_with_no_successor_raise_instead_of_returning_empty():
    """ sysstra-data-services dropped these three with no replacement. Failing loudly beats
    a swallowed [] that reads as 'no data for this range'. """
    for call in (lambda: historical.fetch_option_candles_by_symbol("NIFTY", "X", "2024-01-01", "2024-01-02"),
                 lambda: historical.fetch_option_candles_by_date("NIFTY", "2024-01-01", "2024-01-02"),
                 lambda: historical.fetch_option_candle_by_timestamp("NIFTY", 22000, "CE", "2024-01-01 10:00:00")):
        try:
            call()
        except NotImplementedError:
            continue
        raise AssertionError("expected NotImplementedError")
