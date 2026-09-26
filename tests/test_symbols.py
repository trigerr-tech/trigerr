""" trigerr.symbols: the canonical symbol grammar and data_key, mirrored
exactly from trigerr-data-collection-in/symbols.py's format_strike and
canonical_symbol (same collector-side tests, PLATFORM_TARGET_ARCHITECTURE.md
secs 3.2-3.3). """
from datetime import datetime

import pytest

from trigerr import symbols


# --- format_strike: exact, lossless, never scientific notation -------------

@pytest.mark.parametrize("strike, expected", [
    (23050.0, "23050"),
    (162.5, "162.5"),
    (72.25, "72.25"),
    (150000.0, "150000"),
    (1.0, "1"),
])
def test_format_strike(strike, expected):
    assert symbols.format_strike(strike) == expected


# --- canonical_symbol: one name per instrument type, per the grammar -------

def test_canonical_symbol_equity_is_the_underlying_name_as_is():
    assert symbols.canonical_symbol("EQUITY", "RELIANCE") == "RELIANCE"


def test_canonical_symbol_index_replaces_spaces_with_underscores():
    assert symbols.canonical_symbol("INDEX", "NIFTY 50") == "NIFTY_50"


def test_canonical_symbol_futures():
    expiry = datetime(2026, 9, 25)
    assert symbols.canonical_symbol("FUTURES", "NIFTY", expiry) == "NIFTY_FUTURES_2026-09-25"


def test_canonical_symbol_option_with_fractional_strike():
    expiry = datetime(2026, 9, 25)
    assert (symbols.canonical_symbol("OPTION", "NIFTY", expiry, 162.5, "CE")
           == "NIFTY_162.5_CE_2026-09-25")


def test_canonical_symbol_option_underlying_with_space():
    expiry = datetime(2026, 9, 25)
    assert (symbols.canonical_symbol("OPTION", "NIFTY BANK", expiry, 45000.0, "PE")
           == "NIFTY_BANK_45000_PE_2026-09-25")


# --- data_key: the only place in the SDK a Redis key string is built -------

def test_data_key_upper_cases_only_the_vendor():
    assert symbols.data_key("upstox", "XNSE", "NIFTY_50") == "UPSTOX:XNSE:NIFTY_50"


def test_data_key_option_symbol():
    assert (symbols.data_key("zerodha", "XBSE", "SENSEX_74000_CE_2026-09-25")
           == "ZERODHA:XBSE:SENSEX_74000_CE_2026-09-25")
