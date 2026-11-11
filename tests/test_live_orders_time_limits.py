""" Calls to the OMS carry a time limit, a placement with no answer is resent under its own key until the OMS has
a result for it, and a fill wait that gets no answer keeps waiting: none of these says anything about the order. """
from unittest.mock import MagicMock, patch

import pytest

from trigerr import utils
from trigerr.orders import live

IN_PROGRESS = {"status": "ERROR", "message": "Duplicate request: an order with this idempotency_key is still in progress."}
DONE = {"status": "COMPLETED", "timestamp": "2026-11-11 10:00:00", "filled_quantity": 75, "order_quantity": 75}


def reply(payload, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def setup_function(function):
    live.orders_url = "http://testserver/"


@pytest.fixture
def post():
    with patch("trigerr.orders.live.requests.post") as mock_post, patch("trigerr.orders.live.time.sleep"):
        yield mock_post


def test_every_order_call_has_a_time_limit(post):
    post.return_value = reply(dict(DONE, status="SUCCESS"))
    live.place_live_order("cred-1", {"symbol": "INFY"})
    live.modify_live_order("cred-1", {"order_id": "o1"})
    live.check_order_status("cred-1", "o1", "NFO")
    live.validate_credential("cred-1")
    post.return_value = reply(DONE)
    live.poll_order_status("cred-1", "o1", "NFO")
    limits = [call.kwargs.get("timeout") for call in post.call_args_list]
    assert limits == [live.PLACE_TIMEOUT, live.CALL_TIMEOUT, live.CALL_TIMEOUT, live.CALL_TIMEOUT, live.CALL_TIMEOUT]
    assert all(limit and all(limit) for limit in limits)


def test_the_funds_read_has_a_time_limit():
    with patch("trigerr.utils.requests.post") as mock_post:
        mock_post.return_value = reply({"status": "SUCCESS", "message": "Fund Found", "data": {"net_balance": 5.0}})
        assert utils.fetch_available_funds("cred-1") == 5.0
    assert mock_post.call_args.kwargs["timeout"]


@pytest.mark.parametrize("no_answer", [live.requests.Timeout("slow"), reply("<html>bad gateway</html>", 502), reply({}, 504)])
def test_a_placement_with_no_answer_is_resent_under_the_same_key(post, no_answer):
    post.side_effect = [no_answer, reply({"status": "SUCCESS", "order_id": "OID1"})]
    assert live.place_live_order("cred-1", {"symbol": "INFY"})["order_id"] == "OID1"
    keys = [call.kwargs["json"]["idempotency_key"] for call in post.call_args_list]
    assert len(keys) == 2 and keys[0] == keys[1]


def test_a_resent_placement_waits_for_the_first_send_to_finish(post):
    post.side_effect = [live.requests.Timeout("slow"), reply(IN_PROGRESS), reply(IN_PROGRESS),
                        reply({"status": "SUCCESS", "order_id": "OID1"})]
    assert live.place_live_order("cred-1", {"symbol": "INFY"})["order_id"] == "OID1"
    keys = {call.kwargs["json"]["idempotency_key"] for call in post.call_args_list}
    assert post.call_count == 4 and len(keys) == 1


def test_the_wait_for_the_first_send_is_bounded(post):
    post.side_effect = [live.requests.Timeout("slow")] + [reply(IN_PROGRESS)] * 50
    clock = iter(range(0, 10000, 10))
    with patch("trigerr.orders.live.time.monotonic", side_effect=lambda: next(clock)):
        answer = live.place_live_order("cred-1", {"symbol": "INFY"})
    assert answer == IN_PROGRESS
    assert post.call_count < 50


def test_a_plain_refusal_is_not_resent(post):
    post.return_value = reply({"status": "ERROR", "message": "Insufficient funds"})
    assert live.place_live_order("cred-1", {"symbol": "INFY"})["message"] == "Insufficient funds"
    assert post.call_count == 1


@pytest.mark.parametrize("no_answer", [live.requests.ConnectionError("reset"), live.requests.Timeout("slow"),
                                       reply("<html>bad gateway</html>", 502)])
def test_a_fill_wait_with_no_answer_keeps_waiting(post, no_answer):
    post.side_effect = [reply({"status": "OPEN"}), no_answer, no_answer, reply(DONE)]
    waits = []
    status, order = live.poll_order_status("cred-1", "OID1", "NFO", on_wait=lambda: waits.append(1))
    assert status == "success" and order["filled_quantity"] == 75
    assert len(waits) == 3


def test_a_fill_wait_with_no_answer_still_ends_at_its_time_limit(post):
    post.side_effect = live.requests.ConnectionError("down")
    clock = iter(range(0, 100000, 100))
    with patch("trigerr.orders.live.time.time", side_effect=lambda: next(clock)):
        status, order = live.poll_order_status("cred-1", "OID1", "NFO", max_wait_seconds=1000)
    assert status == "timeout" and order is None
