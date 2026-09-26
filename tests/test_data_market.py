""" trigerr.data.market: resolve_data_source (PLATFORM_TARGET_ARCHITECTURE.md
sec 5) and the ltp/candles/last_candle/candle_stream reads over the shared
Redis contract (sec 6). Uses small hand-rolled fakes (fakeredis isn't
importable in this environment) covering exactly the get/set/xrange/
xrevrange/xread surface these functions touch. """
import datetime
import json

import pytest

from trigerr.data import market


MARKET_CONFIG = {"primary_vendor": "upstox", "sources": ["upstox", "zerodha"]}


# ---------------------------------------------------------------------------
# resolve_data_source
# ---------------------------------------------------------------------------

def test_resolve_data_source_pin_wins_even_for_an_lt_request_with_a_broker():
    request = {"data_vendor": "zerodha", "mode": "lt"}
    assert market.resolve_data_source(request, MARKET_CONFIG, broker="upstox") == "zerodha"


def test_resolve_data_source_lt_uses_the_broker_when_it_is_a_source():
    request = {"mode": "lt"}
    assert market.resolve_data_source(request, MARKET_CONFIG, broker="zerodha") == "zerodha"


def test_resolve_data_source_lt_broker_not_a_source_falls_back_to_primary():
    request = {"mode": "lt"}
    assert market.resolve_data_source(request, MARKET_CONFIG, broker="dhan") == "upstox"


def test_resolve_data_source_vt_ignores_the_broker():
    request = {"mode": "vt"}
    assert market.resolve_data_source(request, MARKET_CONFIG, broker="zerodha") == "upstox"


def test_resolve_data_source_no_pin_no_broker_uses_primary():
    assert market.resolve_data_source({"mode": "bt"}, MARKET_CONFIG) == "upstox"


def test_resolve_data_source_unknown_vendor_raises_naming_vendor_and_sources():
    with pytest.raises(ValueError) as exc:
        market.resolve_data_source({"data_vendor": "coinbase"}, MARKET_CONFIG)
    assert "coinbase" in str(exc.value)
    assert "upstox" in str(exc.value) and "zerodha" in str(exc.value)


# ---------------------------------------------------------------------------
# ltp / candles / last_candle -- a small fake covering get/set/xrange/xrevrange
# ---------------------------------------------------------------------------

class FakeRedis:
    def __init__(self):
        self.strings = {}
        self.streams = {}

    def get(self, key):
        return self.strings.get(key)

    def set(self, key, value, ex=None):
        self.strings[key] = value

    def xadd_candle(self, stream_key, candle):
        """ Test helper, not a real redis-py method: seeds one closed candle. """
        entries = self.streams.setdefault(stream_key, [])
        entry_id = f"{len(entries) + 1}-1"
        entries.append((entry_id, {"c": json.dumps(candle, default=str)}))
        return entry_id

    def xrange(self, key, start, end):
        return list(self.streams.get(key, []))

    def xrevrange(self, key, count=None):
        entries = list(reversed(self.streams.get(key, [])))
        return entries[:count] if count else entries


def test_ltp_parses_datetimes_and_returns_none_when_absent():
    cursor = FakeRedis()
    tick = {"data_key": "UPSTOX:XNSE:NIFTY_50", "symbol": "NIFTY_50", "last_price": 100,
           "ts_exchange": "2026-01-01 09:20:00", "ts_recv": "2026-01-01 09:20:00.123456"}
    cursor.set("UPSTOX:XNSE:NIFTY_50:ltp", json.dumps(tick))

    parsed = market.ltp(cursor, "UPSTOX:XNSE:NIFTY_50")
    assert parsed["ts_exchange"] == datetime.datetime(2026, 1, 1, 9, 20, 0)
    assert parsed["ts_recv"] == datetime.datetime(2026, 1, 1, 9, 20, 0, 123456)
    assert parsed["last_price"] == 100

    assert market.ltp(cursor, "UPSTOX:XNSE:MISSING") is None


def test_candles_parses_every_closed_candle_and_empty_list_when_absent():
    cursor = FakeRedis()
    cursor.xadd_candle("UPSTOX:XNSE:NIFTY_50:candle:1m",
                       {"timestamp": "2026-01-01 09:00:00", "close": 1})
    cursor.xadd_candle("UPSTOX:XNSE:NIFTY_50:candle:1m",
                       {"timestamp": "2026-01-01 09:01:00", "close": 2})

    result = market.candles(cursor, "UPSTOX:XNSE:NIFTY_50", "1m")
    assert [c["close"] for c in result] == [1, 2]
    assert result[0]["timestamp"] == datetime.datetime(2026, 1, 1, 9, 0, 0)

    assert market.candles(cursor, "UPSTOX:XNSE:MISSING", "1m") == []


def test_last_candle_returns_the_newest_and_none_when_absent():
    cursor = FakeRedis()
    cursor.xadd_candle("UPSTOX:XNSE:NIFTY_50:candle:1m",
                       {"timestamp": "2026-01-01 09:00:00", "close": 1})
    cursor.xadd_candle("UPSTOX:XNSE:NIFTY_50:candle:1m",
                       {"timestamp": "2026-01-01 09:01:00", "close": 2})

    newest = market.last_candle(cursor, "UPSTOX:XNSE:NIFTY_50", "1m")
    assert newest["close"] == 2
    assert newest["timestamp"] == datetime.datetime(2026, 1, 1, 9, 1, 0)

    assert market.last_candle(cursor, "UPSTOX:XNSE:MISSING", "1m") is None


# ---------------------------------------------------------------------------
# candle_stream -- scripted XREAD responses/exceptions, one per call
# ---------------------------------------------------------------------------

class ScriptedRedis:
    """ Returns each of `steps` in order, one per xread() call -- an entry is
    either an exception to raise or an XREAD-shaped response. Records the
    `streams` argument of every call so the resume logic (passing the
    remembered id forward, not "$", after a reconnect) can be asserted. """

    def __init__(self, steps, newest=None):
        self._steps = list(steps)
        self.calls = []
        self._newest = newest or {}

    def xrevrange(self, stream, count=None):
        """ The stream's newest entry, as pinned before the first read. """
        return [(self._newest[stream], {})] if stream in self._newest else []

    def xread(self, streams, block=None):
        self.calls.append(dict(streams))
        step = self._steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def _entry(entry_id, candle):
    return (entry_id, {"c": json.dumps(candle, default=str)})


def test_candle_stream_yields_in_order_from_the_start_of_a_new_stream():
    c1 = {"timestamp": "2026-01-01 09:00:00", "close": 1}
    c2 = {"timestamp": "2026-01-01 09:01:00", "close": 2}
    cursor = ScriptedRedis([
        [("K:candle:1m", [_entry("1-1", c1), _entry("1-2", c2)])],
    ])
    gen = market.candle_stream(cursor, ["K"], "1m")

    got = [next(gen), next(gen)]
    assert [candle["close"] for _, candle in got] == [1, 2]
    # no such stream yet when the generator starts -> read it from its start
    assert cursor.calls[0] == {"K:candle:1m": "0-0"}


def test_candle_stream_pins_an_existing_stream_to_its_newest_id_not_dollar():
    c1 = {"timestamp": "2026-01-01 09:05:00", "close": 5}
    cursor = ScriptedRedis([None, [("K:candle:1m", [_entry("9-1", c1)])]],
                           newest={"K:candle:1m": "9-0"})
    gen = market.candle_stream(cursor, ["K"], "1m")
    assert next(gen)[1]["close"] == 5
    # both reads -- before and after the empty BLOCK timeout -- use the pinned
    # id; a literal "$" on the second call would skip anything written between
    assert cursor.calls == [{"K:candle:1m": "9-0"}, {"K:candle:1m": "9-0"}]


def test_candle_stream_empty_response_just_loops(monkeypatch):
    c1 = {"timestamp": "2026-01-01 09:00:00", "close": 1}
    cursor = ScriptedRedis([
        None,  # a BLOCK timeout with nothing new
        [("K:candle:1m", [_entry("1-1", c1)])],
    ])
    gen = market.candle_stream(cursor, ["K"], "1m")
    data_key, candle = next(gen)
    assert candle["close"] == 1
    assert len(cursor.calls) == 2


def test_candle_stream_resumes_after_connection_error_without_gap_or_duplicate(monkeypatch):
    monkeypatch.setattr(market.time, "sleep", lambda *_a, **_k: None)
    c1 = {"timestamp": "2026-01-01 09:00:00", "close": 1}
    c2 = {"timestamp": "2026-01-01 09:01:00", "close": 2}
    c3 = {"timestamp": "2026-01-01 09:02:00", "close": 3}
    cursor = ScriptedRedis([
        [("K:candle:1m", [_entry("1-1", c1)])],
        ConnectionError("dropped"),
        [("K:candle:1m", [_entry("2-1", c2), _entry("2-2", c3)])],
    ])
    gen = market.candle_stream(cursor, ["K"], "1m")

    got = [next(gen), next(gen), next(gen)]
    assert [candle["close"] for _, candle in got] == [1, 2, 3]
    # the retry after the ConnectionError must resume from the last id this
    # generator actually saw ("1-1"), never restart from "$" (a gap) or
    # re-read something already yielded (a duplicate).
    assert cursor.calls[1] == {"K:candle:1m": "1-1"}
    assert cursor.calls[2] == {"K:candle:1m": "1-1"}


def test_candle_stream_retries_redis_py_connection_errors(monkeypatch):
    """ redis-py's ConnectionError is not a builtin ConnectionError subclass --
    the retry must still catch it, or a real dropped connection kills the feed. """
    import redis.exceptions
    monkeypatch.setattr(market.time, "sleep", lambda *_a, **_k: None)
    c1 = {"timestamp": "2026-01-01 09:00:00", "close": 1}
    cursor = ScriptedRedis([redis.exceptions.ConnectionError("dropped"),
                            [("K:candle:1m", [_entry("1-1", c1)])]])
    gen = market.candle_stream(cursor, ["K"], "1m")
    assert next(gen)[1]["close"] == 1


def test_candle_stream_reraises_after_five_consecutive_failures(monkeypatch):
    monkeypatch.setattr(market.time, "sleep", lambda *_a, **_k: None)
    cursor = ScriptedRedis([TimeoutError("t") for _ in range(5)])
    gen = market.candle_stream(cursor, ["K"], "1m")
    with pytest.raises(TimeoutError):
        next(gen)
