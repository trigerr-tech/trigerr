from .config import config

__version__ = "0.6.0"


def set_api_key(key):
    """ Function to set the data-services api key """
    config["api_key"] = key


def set_orders_api_key(key):
    """ Function to set the orders API key """
    config["orders_api_key"] = key


def set_data_url(url):
    """ Function to set data url """
    config["data_url"] = url


def set_orders_url(url):
    """ Function to set Orders URL """
    config["orders_url"] = url
