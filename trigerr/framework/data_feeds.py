""" DATA_FEED_KINDS: one resolver per data source a strategy can declare in
its FEEDS block. Each resolver is `fetch_historical(feed_spec, ctx) -> rows`
— a list of dict candles for market-data kinds, or the raw stored value for
collection/model kinds.

Candle-kind resolvers call the SDK's own HTTP-based historical fetchers
directly — pure, no Redis/Mongo. `mongo_collection`/`pickled_model` read
whatever the runtime already placed on ctx (`ctx["collections"]`/
`ctx["models"]`) instead of importing pymongo/pickle here — the same pattern
`instrument.py` already uses for broker/symbol metadata, and what keeps this
package infra-free (Decision #8: the SDK is the pure core; live/DB access is
an engine-side adapter).

`resolve_feeds` is the entry point: it resolves every declared feed — base
feeds via a DATA_FEED_KINDS resolver, derived feeds via a CANDLE_TRANSFORMS
function applied to their base feed's rows — in dependency order, each
computed exactly once per run. Adding a new data source (ticks, FII/DII
flows, an options chain) is one function + one entry here, no change to
resolve_feeds or the compiler — the generality gate. """

import datetime

import pandas as pd

from trigerr.data.historical import (
    fetch_eod_candles, fetch_index_candles, fetch_futures_candle, fetch_option_candles,
)
from trigerr.utils import apply_indicators
from trigerr.framework.compiler import topological_feed_order, resolve_parameter_references
from trigerr.framework.candle_transforms import CANDLE_TRANSFORMS


def _lookback_window(feed_spec, ctx):
    end_date = ctx.get("as_of_date", datetime.date.today())
    start_date = end_date - datetime.timedelta(days=feed_spec.get("lookback_days", 365))
    return start_date, end_date


def _apply_declared_indicators(rows, feed_spec):
    indicators_spec = feed_spec.get("indicators")
    if not indicators_spec or not rows:
        return rows
    return apply_indicators(dataframe=pd.DataFrame(rows), indicators_dict=indicators_spec).to_dict("records")


def _fetch_eod(feed_spec, ctx):
    start_date, end_date = _lookback_window(feed_spec, ctx)
    rows = fetch_eod_candles(symbol=feed_spec["symbol"], start_date=start_date, end_date=end_date,
                              exchange=feed_spec.get("exchange", "XNSE"))
    return _apply_declared_indicators(rows, feed_spec)


def _fetch_intraday_candles(feed_spec, ctx):
    start_date, end_date = _lookback_window(feed_spec, ctx)
    rows = fetch_index_candles(symbol=feed_spec["symbol"], start_date=start_date, end_date=end_date,
                                granularity=feed_spec.get("granularity", 1),
                                exchange=feed_spec.get("exchange", "XNSE"))
    return _apply_declared_indicators(rows, feed_spec)


def _fetch_futures(feed_spec, ctx):
    start_date, end_date = _lookback_window(feed_spec, ctx)
    rows = fetch_futures_candle(underlying=feed_spec["symbol"], start_date=start_date, end_date=end_date,
                                granularity=feed_spec.get("granularity", 1),
                                exchange=feed_spec.get("exchange", "XNSE"))
    return _apply_declared_indicators(rows, feed_spec)


def _fetch_options(feed_spec, ctx):
    start_date, end_date = _lookback_window(feed_spec, ctx)
    rows = fetch_option_candles(underlying=feed_spec["symbol"], start_date=start_date, end_date=end_date,
                                option_type=feed_spec["option_type"], strike_price=feed_spec["strike_price"],
                                expiry=feed_spec.get("expiry", "current"),
                                granularity=feed_spec.get("granularity", 1),
                                exchange=feed_spec.get("exchange", "XNSE"))
    return _apply_declared_indicators(rows, feed_spec)


def _fetch_mongo_collection(feed_spec, ctx):
    return ctx["collections"][feed_spec["name"]]


def _fetch_pickled_model(feed_spec, ctx):
    """ A model is a single object, not a candle series — a "ref" op can't
    read it; a native node's plugin reads ctx["feeds"][name] directly. """
    return ctx["models"][feed_spec["path"]]


DATA_FEED_KINDS = {
    "eod": {"fetch_historical": _fetch_eod,
            "spec": {"label": "End-of-day candles", "params": ["symbol", "lookback_days", "exchange"]}},
    "intraday_candles": {"fetch_historical": _fetch_intraday_candles,
                          "spec": {"label": "Intraday index/spot candles",
                                   "params": ["symbol", "granularity", "exchange"]}},
    "futures": {"fetch_historical": _fetch_futures,
                "spec": {"label": "Futures candles", "params": ["symbol", "granularity", "exchange"]}},
    "options": {"fetch_historical": _fetch_options,
                "spec": {"label": "Option candles",
                         "params": ["symbol", "option_type", "strike_price", "expiry", "granularity"]}},
    "mongo_collection": {"fetch_historical": _fetch_mongo_collection,
                          "spec": {"label": "Mongo collection (e.g. nse_pre_open)", "params": ["name"]}},
    "pickled_model": {"fetch_historical": _fetch_pickled_model,
                       "spec": {"label": "Pickled ML model", "params": ["path"]}},
}


def resolve_feeds(ast, ctx):
    """ Resolves every declared feed into {name: rows}, in dependency order,
    each computed exactly once. $-sugared feed spec values are substituted
    from ctx["parameters"] before either a DATA_FEED_KINDS resolver or a
    CANDLE_TRANSFORMS function sees them. """
    feeds = {}
    for name in topological_feed_order(ast["feeds"]):
        feed_spec = resolve_parameter_references(ast["feeds"][name], ctx["parameters"])
        if "derive" in feed_spec:
            base_rows = feeds[feed_spec["derive"]]
            feeds[name] = CANDLE_TRANSFORMS[feed_spec["transform"]]["apply"](base_rows, feed_spec)
        else:
            feeds[name] = DATA_FEED_KINDS[feed_spec["kind"]]["fetch_historical"](feed_spec, ctx)
    return feeds
