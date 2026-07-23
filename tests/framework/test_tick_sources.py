import datetime
import json

from trigerr.framework.tick_sources import live_pubsub_ticks, clock_feed_ticks_live


class _FakePubSub:
    def __init__(self, messages):
        self.messages = messages

    def subscribe(self, channel):
        self.subscribed_to = channel

    def listen(self):
        yield from self.messages


class _FakeRedis:
    def __init__(self, messages):
        self._pubsub = _FakePubSub(messages)

    def pubsub(self):
        return self._pubsub


def _message(candle):
    return {"data": json.dumps(candle).encode()}


def test_live_pubsub_ticks_decodes_and_skips_noise():
    messages = [None, {"data": "not-bytes"}, _message({"close": 10}), _message({"close": 11})]
    redis_cursor = _FakeRedis(messages)
    ticks = list(live_pubsub_ticks(redis_cursor, "NIFTY_candle_1min"))
    assert ticks == [{"close": 10}, {"close": 11}]
    assert redis_cursor._pubsub.subscribed_to == "NIFTY_candle_1min"


def test_clock_feed_ticks_live_appends_and_yields_feeds_view():
    """ feeds_view IS ctx["feeds"] (accumulating, not a fresh truncated copy
    per tick) - so each yielded moment must be inspected immediately, exactly
    how wait_for_entry_signal/monitor_open_position consume it, not collected
    via list() first. """
    candle_1 = {"symbol": "NIFTY", "timestamp": "2026-01-01 09:00:00", "close": 100}
    candle_2 = {"symbol": "NIFTY", "timestamp": "2026-01-01 09:01:00", "close": 101}
    redis_cursor = _FakeRedis([_message(candle_1), _message(candle_2)])

    ctx = {"clock_feed": "spot", "feeds": {"spot": []}}
    generator = clock_feed_ticks_live(ctx, redis_cursor, "NIFTY_candle_1min")

    moment_1, feeds_view_1 = next(generator)
    assert moment_1 == datetime.datetime(2026, 1, 1, 9, 0)
    assert len(feeds_view_1["spot"]) == 1
    assert feeds_view_1 is ctx["feeds"]

    moment_2, feeds_view_2 = next(generator)
    assert moment_2 == datetime.datetime(2026, 1, 1, 9, 1)
    assert len(feeds_view_2["spot"]) == 2


def test_clock_feed_ticks_live_maps_last_price_to_close():
    candle = {"symbol": "NIFTY", "timestamp": "2026-01-01 09:00:00", "last_price": 105}
    redis_cursor = _FakeRedis([_message(candle)])
    ctx = {"clock_feed": "spot", "feeds": {"spot": []}}
    _, feeds_view = next(clock_feed_ticks_live(ctx, redis_cursor, "chan"))
    assert feeds_view["spot"][0]["close"] == 105
