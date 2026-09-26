""" The vt/lt half of CLOCK-driven evaluation (Decision #12); the bt half is
clock.iterate_clock_bt. `clock_feed_ticks_live` adapts the candle-stream
market-data plane (trigerr.data.market.candle_stream) to the SAME shape
iterate_clock_bt yields — (moment, feeds_view) — which is what makes
wait_for_entry_signal/monitor_open_position one identical loop regardless of
mode (the actual "one execution core" property). No truncation happens here:
a live feed only ever holds candles that have already arrived. """

from trigerr.data.market import candle_stream


def clock_feed_ticks_live(ctx, redis_cursor, data_key, tf="1m"):
    """ Appends each incoming candle to ctx["feeds"][ctx["clock_feed"]] and
    yields (moment, ctx["feeds"]) — the live-mode counterpart to
    clock.iterate_clock_bt. Sources from candle_stream over data_key's own
    K:candle:{tf}; candle_stream already parses the candle's timestamp and
    every candle carries a native close, so no last_price/timestamp
    normalization is needed here. """
    clock_feed = ctx["clock_feed"]
    for _, candle in candle_stream(redis_cursor, [data_key], tf):
        ctx["feeds"].setdefault(clock_feed, []).append(candle)
        yield candle["timestamp"], ctx["feeds"]
