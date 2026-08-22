""" Pins the log envelope against tests/fixtures/envelope.golden.json.

That fixture is the SAME FILE in project-sysstra's sysstra-logging and
project-trigerr's trigerr. Both projects push into one Loki, so a dashboard
or alert written against one has to work against the other — and the two
copies of logging_utils.py have drifted before, while a comment in CLAUDE.md
asked politely for them to stay in sync. This test is that comment with
teeth: change the envelope in one project and its own suite fails until the
fixture is updated in both.

Changing the envelope on purpose = edit the fixture in BOTH repos and bump
SCHEMA_VERSION so mid-rollout lines stay distinguishable in Loki.
"""
import io
import json
import logging
import os

import pytest

import trigerr_logging as lu

GOLDEN = os.path.join(os.path.dirname(__file__), "fixtures", "envelope.golden.json")


@pytest.fixture(scope="module")
def golden():
    with open(GOLDEN) as f:
        return json.load(f)


@pytest.fixture(autouse=True)
def _clean_context():
    lu.clear_context()
    yield
    lu.clear_context()


def _render(service="svc", extra=None):
    logger = logging.getLogger("parity")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(lu.JsonFormatter(service))
    logger.addHandler(handler)
    logger.info("hello", extra=extra or {})
    return json.loads(buf.getvalue().strip().splitlines()[-1])


def test_schema_version_matches_golden(golden):
    assert lu.SCHEMA_VERSION == golden["schema_version"]


def test_identity_fields_match_golden(golden):
    assert list(lu.IDENTITY_FIELDS) == golden["identity"]


def test_intrinsic_fields_match_golden(golden):
    assert sorted(lu._INTRINSIC_FIELDS) == sorted(golden["intrinsic"])


def test_env_backed_fields_match_golden(golden):
    assert lu._ENV_FIELDS == golden["env_backed"]


def test_domain_field_order_matches_golden(golden):
    assert list(lu._DOMAIN_ORDER) == golden["domain"]


def test_env_default_matches_golden(golden):
    assert lu._DEFAULT_ENV == golden["defaults"]["env"]


def test_rendered_line_starts_with_the_golden_identity_block(golden, monkeypatch):
    """ The fixture lists names; this asserts the formatter actually emits
    them, in order, ahead of everything else. """
    for var in ("SERVICE", "ENVIRONMENT", "TENANT", "MARKET"):
        monkeypatch.delenv(var, raising=False)
    rec = _render()
    assert list(rec)[:len(golden["identity"])] == golden["identity"]


def test_domain_fields_are_never_padded(golden):
    """ The counterpart to the identity block: a repo that has no concept of
    a field must not emit it blank, or a consumer cannot tell that apart
    from a repo that has the concept and failed to populate it. """
    rec = _render()
    for field in golden["domain"]:
        assert field not in rec, f"domain field {field} was padded: {rec}"


def test_domain_fields_render_in_golden_order_when_supplied(golden):
    supplied = {"order_id": "o1", "request_id": "r1", "mode": "lt", "job": "j1"}
    rec = _render(extra=supplied)
    emitted = [k for k in rec if k in supplied]
    expected = [f for f in golden["domain"] if f in supplied]
    assert emitted == expected
