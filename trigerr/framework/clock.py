""" CLOCK drives evaluation (Decision #12): a strategy names one feed as its
clock, and evaluation happens once per print of that feed — never a
hardcoded 1-minute subscription baked into the runtime.

`iterate_clock_bt` is the backtest-side half: given fully-resolved historical
feeds, it replays the clock feed's rows in order and yields the
point-in-time-truncated view for each moment — an ordered, deterministic
stream of evaluation moments (Decision #12's "backtest evaluation is a single
deterministic ordered stream of moments"). The vt/lt half (Redis pubsub
driving the same evaluation per live tick) is an engine-side adapter — it
needs a live tick source, which is infra the SDK deliberately does not import
(Decision #8) — and lands with the execution core in Phase 3.

`evaluate_should_trade_today` is the should_run guard (F5 in the earlier
draft): a plugin's check_should_trade_today(ctx) hook, evaluated once after
feeds resolve; the default is always True. """

from trigerr.framework.point_in_time import truncate_feeds_to_moment


def iterate_clock_bt(feeds, clock_feed):
    """ Yields (moment, truncated_feeds) for each row of the clock feed, in
    the order the rows already come in (resolve_feeds/CANDLE_TRANSFORMS
    preserve chronological order throughout). """
    for candle in feeds[clock_feed]:
        moment = candle["timestamp"]
        yield moment, truncate_feeds_to_moment(feeds, moment)


def evaluate_should_trade_today(ctx, plugin):
    """ Runs the plugin's check_should_trade_today guard if it defines one;
    a strategy with no opinion always trades. """
    guard = getattr(plugin, "check_should_trade_today", None)
    return guard(ctx) if guard else True
