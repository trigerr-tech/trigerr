config = {
    "api_key": None,
    "orders_api_key": None,
    "orders_url": None,
    "data_url": None,
    # "orders_url": "http://127.0.0.1:5001/",
    # "data_url": "http://127.0.0.1:5001/"
    }


def get_auth_headers():
    """x-api-key header for orders API calls, set via set_orders_api_key(). The
    orders API authenticates with its own key, separate from the data-services
    api_key. Read at call time (not import time) so a key set after import
    still applies."""
    orders_api_key = config.get("orders_api_key")
    return {"x-api-key": orders_api_key} if orders_api_key else {}
