""" trigerr.framework — the pure strategy-platform core: the canonical AST, the
compiler pipeline, and the execution-support registries (exit conditions,
instrument selectors, position sizers). No Redis/Celery/Mongo imports here —
only plain data and pure functions, so both the engine and the research
backtester can share one definition of what a strategy is. """

from trigerr.framework.compiler import compile_strategy, normalize, resolve, infer_types, \
    infer_subscriptions, validate, lower, is_lookahead_verified
from trigerr.framework.catalog import build_block_catalog
from trigerr.framework.data_feeds import resolve_feeds
from trigerr.framework.point_in_time import truncate_feeds_to_moment
from trigerr.framework.clock import iterate_clock_bt, evaluate_should_trade_today
from trigerr.framework.tick_sources import live_pubsub_ticks, clock_feed_ticks_live
from trigerr.framework.execution_core import (
    wait_for_entry_signal, monitor_open_position, enter_legs, place_entry_order_for_leg,
    place_exit_order_for_leg, convert_leg_orders_to_trade, rebuild_legs_from_open_orders,
    apply_compounding_to_investment, build_leg_order_params,
)
