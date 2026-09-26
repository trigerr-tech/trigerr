""" Live market data over the shared-Redis contract (PLATFORM_TARGET_ARCHITECTURE.md
secs 5-6). Every function is dependency-injected on an already-connected Redis
cursor, same pattern as the rest of this codebase -- nothing here imports redis
itself. Replaces trigerr/data/live.py's nine functions and their `all_symbols:`
key format wholesale; no compatibility shims. """

import datetime
import json
import time

from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

# redis-py raises its own ConnectionError/TimeoutError, which do not subclass
# the builtins -- catching only the builtins would never retry a real drop.
_RETRYABLE = (ConnectionError, TimeoutError, RedisConnectionError, RedisTimeoutError)


def resolve_data_source(request, market_config, broker=None):
    """ PLATFORM_TARGET_ARCHITECTURE.md sec 5: the vendor a request prices
    from, resolved once at dispatch. Order: the vendor pinned on the request,
    else (lt only) the request's own broker when that vendor is also a data
    source for this market, else the market's tenant default. Pure -- no I/O.
    Raises when the resolved vendor is not one of this market's sources, so a
    request never runs without data. """
    sources = market_config["sources"]
    vendor = request.get("data_vendor")
    if not vendor and request.get("mode") == "lt" and broker in sources:
        vendor = broker
    if not vendor:
        vendor = market_config["primary_vendor"]
    vendor = vendor.lower()
    if vendor not in sources:
        raise ValueError(f"vendor {vendor!r} is not one of this market's sources {sources}")
    return vendor


def _parse_timestamp(value):
    """ Datetimes are serialized with json default=str -- str(datetime), not
    isoformat() (space separator, microseconds only when non-zero). """
    if isinstance(value, datetime.datetime):
        return value
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"unrecognized timestamp: {value!r}")


def _decode(payload):
    if isinstance(payload, bytes):
        payload = payload.decode()
    return json.loads(payload)


def _field(fields, name):
    """ redis-py stream entries come back with bytes keys unless
    decode_responses is set on the connection; the cursor's own setting
    decides which, so accept either. """
    return fields[name] if name in fields else fields[name.encode()]


def _parse_tick(payload):
    tick = _decode(payload)
    for field in ("ts_exchange", "ts_recv"):
        if tick.get(field) is not None:
            tick[field] = _parse_timestamp(tick[field])
    return tick


def _parse_candle(payload):
    candle = _decode(payload)
    if candle.get("timestamp") is not None:
        candle["timestamp"] = _parse_timestamp(candle["timestamp"])
    return candle


def ltp(cursor, data_key):
    """ GET K:ltp -- the tick dict, or None when it isn't set (expired, or
    the lane hasn't ticked yet). """
    payload = cursor.get(f"{data_key}:ltp")
    return None if payload is None else _parse_tick(payload)


def candles(cursor, data_key, tf):
    """ XRANGE K:candle:{tf} - + -- every candle closed so far this session,
    oldest first. [] when the stream doesn't exist yet. """
    entries = cursor.xrange(f"{data_key}:candle:{tf}", "-", "+")
    return [_parse_candle(_field(fields, "c")) for _, fields in entries]


def last_candle(cursor, data_key, tf):
    """ XREVRANGE ... COUNT 1 -- the newest closed candle, or None. """
    entries = cursor.xrevrange(f"{data_key}:candle:{tf}", count=1)
    if not entries:
        return None
    _, fields = entries[0]
    return _parse_candle(_field(fields, "c"))


def _pin_start_ids(cursor, ids):
    """ Resolve each "$" to that stream's current newest id (or "0-0" when the
    stream doesn't exist yet) before the first read. XREAD with "$" means
    "after whatever is newest at the moment of this call", so passing "$"
    again on the next call would drop anything written between two calls
    (e.g. right after a BLOCK timeout) and leave nothing to resume from. """
    for stream, start in ids.items():
        if start == "$":
            newest = cursor.xrevrange(stream, count=1)
            ids[stream] = newest[0][0] if newest else "0-0"


def candle_stream(cursor, data_keys, tf, last_ids=None, block_ms=5000):
    """ XREAD BLOCK over every data_key's K:candle:{tf}, yielding (data_key,
    candle) as each stream gets a new entry. Starts from last_ids[data_key]
    when given, else from the stream's newest entry at the time of the first
    read (a stream that doesn't exist yet is read from its start). Remembers
    the last id read per stream, so a caller that re-enters this generator
    after a redis ConnectionError/TimeoutError resumes with no gap; a timeout
    with no data just loops. Five consecutive failures re-raise. """
    streams = {f"{key}:candle:{tf}": key for key in data_keys}
    ids = {stream: (last_ids or {}).get(key, "$") for stream, key in streams.items()}
    failures = 0

    while True:
        try:
            _pin_start_ids(cursor, ids)
            response = cursor.xread(ids, block=block_ms)
            failures = 0
        except _RETRYABLE:
            failures += 1
            if failures >= 5:
                raise
            time.sleep(min(0.1 * failures, 1))
            continue

        if not response:
            continue

        for stream_name, entries in response:
            stream_name = stream_name.decode() if isinstance(stream_name, bytes) else stream_name
            data_key = streams[stream_name]
            for entry_id, fields in entries:
                ids[stream_name] = entry_id
                yield data_key, _parse_candle(_field(fields, "c"))
