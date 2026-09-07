""" Reference data (symbols, contract expiries) from sysstra-data-services.

Unlike historical.py, nothing here swallows exceptions. These are start-of-run
lookups whose result configures an entire backtest or trading run: returning {} on
failure would be indistinguishable from "no such symbol", and the caller would
proceed with a silently wrong exchange, market or lot size.
"""
from collections import Counter

from trigerr.data.historical import _get_client


def fetch_symbol(symbol, exchange=None):
    """ One symbol's reference record: exchange, market, lot_size, tick_size, ... """
    return _get_client().market.symbol(symbol=symbol, exchange=exchange)


def fetch_expiries(exchange, underlying, instrument_type="OPTIONS", expiry_date=None, status="active"):
    """ Contract expiries for an underlying, each with its own lot_size and strike ladder. """
    return _get_client().market.expiries(exchange=exchange, underlying=underlying,
                                         instrument_type=instrument_type,
                                         expiry_date=expiry_date, status=status)


def strike_difference_from(contract):
    """ The strike ladder's step, as the most common gap between adjacent strikes.

    Modal rather than minimal: real ladders are denser near the money and sparser in
    the wings, so min() would report the tightest local step instead of the standard one.
    """
    strikes = sorted(s["strike"] for s in (contract.get("strikes") or []) if s.get("strike") is not None)
    if len(strikes) < 2:
        return None
    gaps = [round(b - a, 6) for a, b in zip(strikes, strikes[1:]) if b > a]
    return Counter(gaps).most_common(1)[0][0] if gaps else None
