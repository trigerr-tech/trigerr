import trigerr


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

