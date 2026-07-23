import datetime

from trigerr.framework.point_in_time import truncate_feeds_to_moment


def _candle(minute, close):
    return {"timestamp": datetime.datetime(2026, 1, 1, 9, minute), "close": close}


def test_truncates_timestamped_rows_to_the_moment():
    feeds = {"spot": [_candle(0, 10), _candle(1, 11), _candle(2, 12), _candle(3, 13)]}
    truncated = truncate_feeds_to_moment(feeds, datetime.datetime(2026, 1, 1, 9, 1))
    assert [row["close"] for row in truncated["spot"]] == [10, 11]


def test_a_cheating_strategy_cannot_see_a_bar_ahead_through_a_declared_feed():
    """ The lookahead test from Gate 3: even though the feed was resolved with
    its FULL history upfront, a moment-scoped view never exposes a future bar. """
    feeds = {"daily": [_candle(0, 100), _candle(1, 105), _candle(2, 999)]}
    truncated = truncate_feeds_to_moment(feeds, datetime.datetime(2026, 1, 1, 9, 1))
    values = [row["close"] for row in truncated["daily"]]
    assert 999 not in values
    assert values == [100, 105]


def test_non_timestamped_feeds_pass_through_unchanged():
    feeds = {"breadth": [{"advances": 10, "declines": 5}], "model": "loaded-model-object"}
    truncated = truncate_feeds_to_moment(feeds, datetime.datetime(2026, 1, 1, 9, 0))
    assert truncated == feeds


def test_empty_feed_passes_through():
    feeds = {"spot": []}
    assert truncate_feeds_to_moment(feeds, datetime.datetime(2026, 1, 1)) == {"spot": []}
