""" The live tick source across the entry -> monitor hand-off.

run_strategy (engine) opens the live clock twice per position: once to wait for the entry signal, and again,
after the legs are placed, to monitor the position. Each open starts `candle_stream` at "$" — "whatever is newest
at the first read" — so a candle that closes while the legs are being placed (serial legging, order polling) falls
between the two and is never seen: not added to the clock feed, never exit-evaluated.

This drives the REAL `clock_feed_ticks_live` and the REAL `candle_stream` against a fake Redis that implements
only the stream commands they use, so the test pins behaviour, not an implementation.
"""
import datetime
import json

import pytest

import trigerr.framework as fw

KEY = "UPSTOX:XNSE:NIFTY_50"
STREAM = f"{KEY}:candle:1m"


class Drained(Exception):
    """ Raised by the fake when a reader would block forever with nothing left to deliver. """


class FakeStream:
    """ The two stream commands candle_stream uses (xrevrange, xread) over one list. A candle can land while
    nobody is reading (`arrive`), or during a blocked read: an xread with nothing new delivers the next scripted
    candle, and raises Drained when the script is empty. """
    def __init__(self, history, script):
        self.entries = []
        self.script = list(script)
        for candle in history:
            self._append(candle)

    def _append(self, candle):
        number = len(self.entries) + 1
        self.entries.append((f"{number}-0", {"c": json.dumps(candle)}))

    def arrive(self):
        self._append(self.script.pop(0))

    def xrevrange(self, stream, count=1):
        return list(reversed(self.entries))[:count]

    def xread(self, ids, block=None):
        after = int(ids[STREAM].split("-")[0])
        new = [e for e in self.entries if int(e[0].split("-")[0]) > after]
        if not new and self.script:
            self.arrive()
            new = [self.entries[-1]]
        if not new:
            raise Drained()
        return [(STREAM, new)]


def _candle(minute, close=100):
    return {"symbol": "NIFTY_50", "timestamp": f"2025-06-02 09:{minute:02d}:00", "open": close, "high": close,
            "low": close, "close": close}


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="S3: each live tick source opens candle_stream at '$', so a candle that closed while the "
                          "legs were placed is skipped and monitoring starts one candle late")
def test_a_candle_that_closes_between_entry_and_monitoring_is_not_lost():
    stream = FakeStream(history=[_candle(15)], script=[_candle(16), _candle(17), _candle(18)])
    ctx = {"clock_feed": "spot", "feeds": {}}

    entry_phase = fw.clock_feed_ticks_live(ctx, stream, KEY, "1m")
    moment, _ = next(entry_phase)
    assert moment == datetime.datetime(2025, 6, 2, 9, 16)          # the signal candle: legs are placed now

    stream.arrive()                                                 # 09:17 closes while the legs are being placed

    monitor_phase = fw.clock_feed_ticks_live(ctx, stream, KEY, "1m")
    first_monitored, _ = next(monitor_phase)

    assert first_monitored == datetime.datetime(2025, 6, 2, 9, 17)
    assert [row["timestamp"] for row in ctx["feeds"]["spot"]] == [datetime.datetime(2025, 6, 2, 9, 16),
                                                                  datetime.datetime(2025, 6, 2, 9, 17)]
