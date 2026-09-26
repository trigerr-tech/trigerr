""" Canonical symbol grammar and data keys (PLATFORM_TARGET_ARCHITECTURE.md secs
3.2-3.3). format_strike and canonical_symbol mirror
trigerr-data-collection-in/symbols.py exactly -- collector and SDK must agree
on the same names for the same contract. data_key is the only place in the
SDK a Redis key string is built. """


def format_strike(strike):
    """ Exact, lossless strike rendering -- whole numbers with no decimal
    point, fractional ones with the minimal decimals that reproduce them,
    never scientific notation (an f-string ".10f" only ever expands, never
    switches format like str() does for very large/small floats). """
    text = f"{float(strike):.10f}".rstrip("0").rstrip(".")
    return text


def canonical_symbol(instrument_type, underlying_name, expiry=None, strike=None, option_type=None):
    """ The one canonical name for an instrument, per the platform's symbol
    grammar (PLATFORM_TARGET_ARCHITECTURE.md secs 3-4). """
    underlying = underlying_name.replace(" ", "_")
    if instrument_type == "EQUITY":
        return underlying_name
    if instrument_type == "INDEX":
        return underlying
    tag = expiry.strftime("%Y-%m-%d")
    if instrument_type == "FUTURES":
        return f"{underlying}_FUTURES_{tag}"
    if instrument_type == "OPTION":
        return f"{underlying}_{format_strike(strike)}_{option_type}_{tag}"
    raise ValueError(f"unknown instrument_type {instrument_type!r}")


def data_key(vendor, venue, symbol):
    """ data_key = {VENDOR}:{VENUE}:{symbol}, vendor upper-case
    (PLATFORM_TARGET_ARCHITECTURE.md sec 3.3). """
    return f"{vendor.upper()}:{venue}:{symbol}"
