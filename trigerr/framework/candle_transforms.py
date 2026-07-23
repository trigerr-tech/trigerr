""" CANDLE_TRANSFORMS turns one feed's resolved rows into another feed's rows —
the mechanism behind a strategy's derived feeds (`{"derive": "spot",
"transform": "resample", "granularity": 15}`). Each transform is one function
+ one spec, same registry pattern as everywhere else in this package.

Three of the four wrap SDK functions that already exist rather than
reimplementing them (`convert_candle_pattern`, `change_granularity`); this is
what collapses the 23-file Heikin-Ashi duplication and the six ad-hoc
`*_granularity` inputs into one declared feed each. """

import math

import pandas as pd

from trigerr.utils import convert_candle_pattern, change_granularity, merge_candle


def _rows_to_df(rows):
    df = pd.DataFrame(rows)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def _apply_heikin_ashi(rows, feed_spec):
    if not rows:
        return rows
    return convert_candle_pattern(dataframe=_rows_to_df(rows), pattern="heikin_ashi").to_dict("records")


def _apply_resample(rows, feed_spec):
    if not rows:
        return rows
    return change_granularity(data_df=_rows_to_df(rows), granularity=feed_spec["granularity"]).to_dict("records")


def _apply_merge_doji(rows, feed_spec):
    """ Folds a candle into the previous one whenever its open/close both sit
    inside the previous candle's body — the doji-merge every HKA-trailing
    strategy hand-rolled (`strategy_harness.hka_trailing_after_exits`). """
    if not rows:
        return rows
    merged = [rows[0]]
    for candle in rows[1:]:
        previous = merged[-1]
        body_high = max(previous["open"], previous["close"])
        body_low = min(previous["open"], previous["close"])
        if body_low <= candle["open"] <= body_high and body_low <= candle["close"] <= body_high:
            merged[-1] = merge_candle(candle_1=previous, candle_2=candle)
        else:
            merged.append(candle)
    return merged


def _apply_slope_angle(rows, feed_spec):
    """ Adds a "slope_angle" column: the angle in degrees of the straight
    line from `length` bars ago to the current bar, on `column`. Bars before
    the first full window get None — a real, grounded angle calculation
    (Anurag: "we do angle based value calculations"), not curve-fitted. """
    column = feed_spec.get("column", "close")
    length = feed_spec["length"]
    out = []
    for i, candle in enumerate(rows):
        new_candle = dict(candle)
        if i >= length:
            rise = candle[column] - rows[i - length][column]
            new_candle["slope_angle"] = math.degrees(math.atan2(rise, length))
        else:
            new_candle["slope_angle"] = None
        out.append(new_candle)
    return out


CANDLE_TRANSFORMS = {
    "heikin_ashi": {"apply": _apply_heikin_ashi,
                    "spec": {"label": "Heikin-Ashi candles", "params": []}},
    "resample":    {"apply": _apply_resample,
                    "spec": {"label": "Resample to a coarser granularity", "params": ["granularity"]}},
    "merge_doji":  {"apply": _apply_merge_doji,
                    "spec": {"label": "Merge doji/inside candles", "params": []}},
    "slope_angle": {"apply": _apply_slope_angle,
                    "spec": {"label": "Slope angle over N bars", "params": ["column", "length"]}},
}
