""" build_block_catalog() is the UI palette source: every extensible registry's
specs, generated rather than hardcoded, so a UI never keeps its own copy of
what the platform can do. Adding a block anywhere (an expression op, an exit
condition, an instrument selector, a position sizer, a data feed kind, a
candle transform) means it shows up here automatically, with zero
catalog-side changes. That property is Gate 0. """

from trigerr.framework.expressions import EXPRESSION_OPS
from trigerr.framework.exit_engine import EXIT_CONDITIONS, REQUIRES
from trigerr.framework.instrument import INSTRUMENT_SELECTORS
from trigerr.framework.position_sizing import POSITION_SIZERS
from trigerr.framework.data_feeds import DATA_FEED_KINDS
from trigerr.framework.candle_transforms import CANDLE_TRANSFORMS

_CATEGORIES = {
    "expressions": EXPRESSION_OPS,
    "instrument_selectors": INSTRUMENT_SELECTORS,
    "position_sizers": POSITION_SIZERS,
    "data_feed_kinds": DATA_FEED_KINDS,
    "candle_transforms": CANDLE_TRANSFORMS,
}


def _exit_condition_spec(name, fn):
    """ EXIT_CONDITIONS stays a plain {name: function} registry — as simple
    as data, matching the style it was ported from. Its catalog spec is
    assembled from what already exists elsewhere rather than wrapping every
    function in a dict just to carry a label: the docstring's first line,
    and REQUIRES for the context keys the condition needs. """
    label = (fn.__doc__ or name).strip().splitlines()[0]
    return {"label": label, "params": REQUIRES.get(name, [])}


def build_block_catalog():
    """ Returns {category: {name: spec}} — the UI palette, generated rather
    than hardcoded. """
    catalog = {}
    for category, registry in _CATEGORIES.items():
        catalog[category] = {name: entry["spec"] for name, entry in registry.items()}
    catalog["exit_conditions"] = {name: _exit_condition_spec(name, fn)
                                 for name, fn in EXIT_CONDITIONS.items()}
    return catalog
