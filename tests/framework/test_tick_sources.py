import datetime
import json

from trigerr.framework.tick_sources import clock_feed_ticks_live


class _FakeMarketRedis:
    """ Just enough of the candle-stream surface (trigerr.data.market.candle_stream)
    for clock_feed_ticks_live: one XREAD BLOCK call per batch of entries. """

    def __init__(self, batches):
        # Each batch is {stream_name: [(id, {"c": json_str}), ...]}, delivered
        # one XREAD response at a time, in order.
        self._batches = list(batches)

    def xrevrange(self, stream, count=None):
        # No stream exists before the first batch; candle_stream pins "0-0".
        return []

    def xread(self, streams, block=None):
        if not self._batches:
            return None
        batch = self._batches.pop(0)
        return [(name.encode(), entries) for name, entries in batch.items()]


def _candle_entry(entry_id, candle):
    return (entry_id, {b"c": json.dumps(candle).encode()})


def test_clock_feed_ticks_live_appends_and_yields_feeds_view():
    """ feeds_view IS ctx["feeds"] (accumulating, not a fresh truncated copy
    per tick) - so each yielded moment must be inspected immediately, exactly
    how wait_for_entry_signal/monitor_open_position consume it, not collected
    via list() first. """
    candle_1 = {"symbol": "NIFTY", "timestamp": "2026-01-01 09:00:00", "close": 100}
    candle_2 = {"symbol": "NIFTY", "timestamp": "2026-01-01 09:01:00", "close": 101}
    redis_cursor = _FakeMarketRedis([
        {"UPSTOX:XNSE:NIFTY:candle:1m": [_candle_entry("1-1", candle_1)]},
        {"UPSTOX:XNSE:NIFTY:candle:1m": [_candle_entry("2-1", candle_2)]},
    ])

    ctx = {"clock_feed": "spot", "feeds": {"spot": []}}
    generator = clock_feed_ticks_live(ctx, redis_cursor, "UPSTOX:XNSE:NIFTY", tf="1m")

    moment_1, feeds_view_1 = next(generator)
    assert moment_1 == datetime.datetime(2026, 1, 1, 9, 0)
    assert len(feeds_view_1["spot"]) == 1
    assert feeds_view_1 is ctx["feeds"]

    moment_2, feeds_view_2 = next(generator)
    assert moment_2 == datetime.datetime(2026, 1, 1, 9, 1)
    assert len(feeds_view_2["spot"]) == 2


def test_clock_feed_ticks_live_candle_already_carries_close():
    """ Candle envelopes have a native close (unlike the old pubsub tick
    format) - no last_price->close mapping happens here any more. """
    candle = {"symbol": "NIFTY", "timestamp": "2026-01-01 09:00:00", "close": 105}
    redis_cursor = _FakeMarketRedis([{"UPSTOX:XNSE:NIFTY:candle:1m": [_candle_entry("1-1", candle)]}])
    ctx = {"clock_feed": "spot", "feeds": {"spot": []}}
    _, feeds_view = next(clock_feed_ticks_live(ctx, redis_cursor, "UPSTOX:XNSE:NIFTY", tf="1m"))
    assert feeds_view["spot"][0]["close"] == 105
