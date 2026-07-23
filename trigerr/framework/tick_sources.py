""" The vt/lt half of CLOCK-driven evaluation (Decision #12); the bt half is
clock.iterate_clock_bt. `live_pubsub_ticks` is a pure generator: it takes an
already-connected Redis cursor (dependency-injected, same pattern as every
other cursor in this codebase — the function never imports redis itself) and
yields decoded candle dicts as they arrive.

`clock_feed_ticks_live` adapts that raw stream to the SAME shape
iterate_clock_bt yields — (moment, feeds_view) — which is what makes
wait_for_entry_signal/monitor_open_position one identical loop regardless of
mode (the actual "one execution core" property). No truncation happens here:
a live feed only ever holds candles that have already arrived. """

import datetime
import json


def live_pubsub_ticks(redis_cursor, channel):
    """ Subscribes to `channel` and yields each candle dict as it's published.
    Non-candle pubsub noise (None messages, subscribe-confirmation messages)
    is skipped — the same filter every legacy strategy's listen() loop used. """
    sub = redis_cursor.pubsub()
    sub.subscribe(channel)
    for message in sub.listen():
        if message is None or not isinstance(message, dict) or not isinstance(message.get("data"), bytes):
            continue
        yield json.loads(message["data"])


def _parse_timestamp(value):
    if isinstance(value, datetime.datetime):
        return value
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    raise ValueError(f"unrecognized timestamp: {value!r}")


def _normalize_live_candle(candle):
    candle = dict(candle)
    candle["timestamp"] = _parse_timestamp(candle["timestamp"])
    if candle.get("last_price"):
        candle["close"] = candle["last_price"]
    return candle


def clock_feed_ticks_live(ctx, redis_cursor, channel):
    """ Appends each incoming candle to ctx["feeds"][ctx["clock_feed"]] and
    yields (moment, ctx["feeds"]) — the live-mode counterpart to
    clock.iterate_clock_bt. """
    clock_feed = ctx["clock_feed"]
    for raw_candle in live_pubsub_ticks(redis_cursor, channel):
        candle = _normalize_live_candle(raw_candle)
        ctx["feeds"].setdefault(clock_feed, []).append(candle)
        yield candle["timestamp"], ctx["feeds"]
