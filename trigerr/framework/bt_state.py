""" The state a backtest runs against: an in-process stand-in for the tenant's state Redis.

The execution core keeps a request's orders list, its exit mutex and its pub/sub in
ctx["state_cursor"]. A live or virtual run hands it the real state Redis; a backtest hands it this
instead, so a backtest cannot read or write a real Redis key even by mistake — a stray real call
raises instead of reaching production. It implements only the commands the core and the
orders_utils helpers actually use, and nothing expires (a run is one process).

A plain dict behind closures, not a class, like the rest of the framework. """

import types


def memory_state_cursor():
    store = {}      # key -> str (strings) or list (lists)

    def rpush(key, *values):
        store.setdefault(key, []).extend(values)
        return len(store[key])

    def lrange(key, start, stop):
        items = store.get(key, [])
        return list(items[start:] if stop == -1 else items[start:stop + 1])

    def llen(key):
        return len(store.get(key, []))

    def set_(key, value, nx=False, ex=None):
        if nx and key in store:
            return None
        store[key] = value
        return True

    def get(key):
        value = store.get(key)
        return value if isinstance(value, str) else None

    def delete(key):
        return 1 if store.pop(key, None) is not None else 0

    return types.SimpleNamespace(
        rpush=rpush, lrange=lrange, llen=llen, set=set_, get=get, delete=delete,
        expire=lambda key, seconds: key in store,
        publish=lambda channel, message: 0)
