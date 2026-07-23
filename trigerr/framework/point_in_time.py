""" Point-in-time serving: the platform's core promise (Decision #11) is that
at evaluation moment T a strategy sees only data stamped <= T. `resolve_feeds`
fetches a feed's whole history upfront; `truncate_feeds_to_moment` is what a
backtest replay calls before each simulated moment to get the moment-scoped
view eval_expr is actually allowed to see — this is what makes lookahead
structurally impossible in bt. In vt/lt this is a no-op by construction: a
live feed only ever holds ticks that have already arrived. """


def truncate_feeds_to_moment(feeds, moment):
    """ Returns a new {name: rows} with every timestamped feed's rows
    filtered to timestamp <= moment. A feed whose rows aren't timestamped
    candles (a mongo_collection without a timestamp column, a pickled model
    object) passes through unchanged — truncation only applies where "point
    in time" is a meaningful concept. """
    truncated = {}
    for name, rows in feeds.items():
        if isinstance(rows, list) and rows and isinstance(rows[0], dict) and "timestamp" in rows[0]:
            truncated[name] = [row for row in rows if row["timestamp"] <= moment]
        else:
            truncated[name] = rows
    return truncated
