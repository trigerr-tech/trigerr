config = {
    "api_key": None,
    "orders_url": None,
    "data_url": None,
    # "orders_url": "http://127.0.0.1:5001/",
    # "data_url": "http://127.0.0.1:5001/"
    }


def get_auth_headers():
    """x-api-key header for orders/data API calls, set via set_api_key(). Read
    at call time (not import time) so a key set after import still applies."""
    api_key = config.get("api_key")
    return {"x-api-key": api_key} if api_key else {}
