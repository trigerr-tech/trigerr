import trigerr
from trigerr.config import get_auth_headers


def test_package_exposes_configuration_helpers():
    assert callable(trigerr.set_api_key)
    assert callable(trigerr.set_data_url)
    assert callable(trigerr.set_orders_url)


def test_configuration_helpers_update_package_config():
    trigerr.set_api_key("test-key")
    trigerr.set_data_url("https://data.example.test/")
    trigerr.set_orders_url("https://orders.example.test/")

    assert trigerr.config["api_key"] == "test-key"
    assert trigerr.config["data_url"] == "https://data.example.test/"
    assert trigerr.config["orders_url"] == "https://orders.example.test/"



def test_get_auth_headers_empty_when_no_key_set():
    trigerr.config["api_key"] = None
    assert get_auth_headers() == {}


def test_get_auth_headers_carries_x_api_key_after_set_api_key():
    trigerr.set_api_key("tenant-secret-key")
    assert get_auth_headers() == {"x-api-key": "tenant-secret-key"}
    trigerr.config["api_key"] = None
