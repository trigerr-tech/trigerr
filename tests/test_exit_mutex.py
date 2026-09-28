""" Task B3 (spec §8.3 manual exits): the per-request exit mutex that
serializes everyone who places exit orders for a request — a manual exit
(OMS) and a running strategy's own exits — so a leg is never exited twice.

Offline: a tiny in-memory fake Redis (SET NX EX / GET / DELETE), no network.
"""
import time

from trigerr.orders.orders_utils import acquire_exit_mutex, release_exit_mutex


class FakeRedis:
    def __init__(self):
        self._kv = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self._kv:
            return None
        self._kv[key] = value
        return True

    def get(self, key):
        return self._kv.get(key)

    def delete(self, key):
        return self._kv.pop(key, None) is not None


def test_acquire_returns_a_token_when_free():
    redis_cursor = FakeRedis()
    token = acquire_exit_mutex(redis_cursor, "r1")
    assert token is not None
    assert redis_cursor.get("r1:exit_mutex") == token


def test_acquire_waits_then_succeeds_once_the_holder_releases(monkeypatch):
    redis_cursor = FakeRedis()
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    first_token = acquire_exit_mutex(redis_cursor, "r1")

    # The real SET NX fails while the first holder has it; make the first
    # retry fail, then release before the second retry succeeds.
    attempts = {"n": 0}
    real_set = redis_cursor.set

    def flaky_set(key, value, nx=False, ex=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return None  # still held on the first retry
        redis_cursor.delete("r1:exit_mutex")  # the first holder released it
        return real_set(key, value, nx=nx, ex=ex)

    monkeypatch.setattr(redis_cursor, "set", flaky_set)
    second_token = acquire_exit_mutex(redis_cursor, "r1", wait_s=5)
    assert second_token is not None
    assert second_token != first_token
    assert sleeps, "acquire_exit_mutex must sleep between retries"


def test_acquire_times_out_when_never_released(monkeypatch):
    redis_cursor = FakeRedis()
    acquire_exit_mutex(redis_cursor, "r1")  # holds it forever

    monkeypatch.setattr(time, "sleep", lambda s: None)
    clock = {"t": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["t"])

    # First monotonic() call sets the deadline; make time "pass" fully on the
    # very first is-it-past-the-deadline check so the loop returns None
    # immediately instead of actually looping wait_s/0.2 times.
    real_monotonic = time.monotonic
    calls = {"n": 0}

    def fake_monotonic():
        calls["n"] += 1
        if calls["n"] == 1:
            return 0.0  # deadline = 0.0 + wait_s
        return 10 ** 6  # every later check is long past it
    monkeypatch.setattr(time, "monotonic", fake_monotonic)

    token = acquire_exit_mutex(redis_cursor, "r1", wait_s=1)
    assert token is None


def test_release_deletes_only_when_token_still_matches():
    redis_cursor = FakeRedis()
    token = acquire_exit_mutex(redis_cursor, "r1")
    release_exit_mutex(redis_cursor, "r1", "not-the-token")
    assert redis_cursor.get("r1:exit_mutex") == token  # untouched

    release_exit_mutex(redis_cursor, "r1", token)
    assert redis_cursor.get("r1:exit_mutex") is None


def test_release_is_a_noop_when_key_already_expired_or_gone():
    redis_cursor = FakeRedis()
    release_exit_mutex(redis_cursor, "r1", "whatever")  # must not raise
    assert redis_cursor.get("r1:exit_mutex") is None
