""" Task B3 (spec §8.3 manual exits): the per-request exit mutex that
serializes everyone who places exit orders for a request — a manual exit
(OMS) and a running strategy's own exits — so a leg is never exited twice.

Offline: a tiny in-memory fake Redis (SET NX EX / GET / DELETE), no network.
"""
import time

from trigerr.orders import live
from trigerr.orders.orders_utils import (acquire_exit_mutex, release_exit_mutex, renew_exit_mutex,
                                         EXIT_MUTEX_TTL_S)


class FakeRedis:
    """ SET NX EX / GET / DELETE / EXPIRE with real expiry against a settable
    clock (self.now), so a test can let time pass past the mutex TTL. """
    def __init__(self):
        self._kv = {}
        self._expires = {}
        self.now = 0.0

    def _alive(self, key):
        if key in self._expires and self.now >= self._expires[key]:
            self._kv.pop(key, None)
            self._expires.pop(key, None)
        return key in self._kv

    def set(self, key, value, nx=False, ex=None):
        if nx and self._alive(key):
            return None
        self._kv[key] = value
        if ex is not None:
            self._expires[key] = self.now + ex
        return True

    def get(self, key):
        return self._kv.get(key) if self._alive(key) else None

    def delete(self, key):
        self._expires.pop(key, None)
        return self._kv.pop(key, None) is not None

    def expire(self, key, seconds):
        if not self._alive(key):
            return False
        self._expires[key] = self.now + seconds
        return True


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


# ---------------------------------------------------------------------------
# S5: renewal while an exit order waits for its fill
# ---------------------------------------------------------------------------

def test_renew_extends_the_ttl_for_its_own_token():
    redis_cursor = FakeRedis()
    token = acquire_exit_mutex(redis_cursor, "r1")
    redis_cursor.now = EXIT_MUTEX_TTL_S - 1
    renew_exit_mutex(redis_cursor, "r1", token)
    redis_cursor.now = EXIT_MUTEX_TTL_S + 60  # past the original expiry
    assert redis_cursor.get("r1:exit_mutex") == token


def test_renew_never_touches_someone_elses_mutex():
    redis_cursor = FakeRedis()
    other = acquire_exit_mutex(redis_cursor, "r1")
    redis_cursor.now = EXIT_MUTEX_TTL_S - 1
    renew_exit_mutex(redis_cursor, "r1", "stale-token")
    redis_cursor.now = EXIT_MUTEX_TTL_S
    assert redis_cursor.get("r1:exit_mutex") is None, f"{other} must expire on its own schedule"


def test_renew_does_not_resurrect_an_expired_mutex():
    redis_cursor = FakeRedis()
    token = acquire_exit_mutex(redis_cursor, "r1")
    redis_cursor.now = EXIT_MUTEX_TTL_S + 1
    renew_exit_mutex(redis_cursor, "r1", token)
    assert redis_cursor.get("r1:exit_mutex") is None


def test_an_exit_poll_longer_than_the_ttl_keeps_the_mutex_held(monkeypatch):
    """ A MARKET exit that sits OPEN for 5 minutes (> the 120 s TTL): with
    on_wait renewing, nobody else can take the mutex until the fill. """
    redis_cursor = FakeRedis()
    token = acquire_exit_mutex(redis_cursor, "r1")
    open_polls = {"n": 300}
    seen_free = []

    def fake_post(url, json, headers):
        response = type("R", (), {})()
        status = "OPEN" if open_polls["n"] > 0 else "COMPLETED"
        open_polls["n"] -= 1
        response.json = lambda: {"status": status, "timestamp": "2026-09-28 10:00:00", "average_price": 100.0}
        return response

    def fake_sleep(seconds):
        redis_cursor.now += seconds
        seen_free.append(acquire_exit_mutex(redis_cursor, "r1", wait_s=0) is not None)

    monkeypatch.setattr(live.requests, "post", fake_post)
    monkeypatch.setattr(live.time, "sleep", fake_sleep)
    monkeypatch.setattr(live.time, "time", lambda: redis_cursor.now)
    live.orders_url = "http://testserver/"

    status, _ = live.poll_order_status("c1", "OID1", "NFO",
                                       on_wait=lambda: renew_exit_mutex(redis_cursor, "r1", token))
    assert status == "success"
    assert redis_cursor.now >= 300
    assert not any(seen_free), "the mutex must never be free while the exit is still OPEN"
    assert redis_cursor.get("r1:exit_mutex") == token
