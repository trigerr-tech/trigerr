from unittest.mock import MagicMock, patch

from trigerr import logging_utils as lu
from trigerr.orders import live


def _mock_response(payload):
    response = MagicMock()
    response.json.return_value = payload
    return response


def setup_function(_):
    lu.clear_context()
    # orders_url is bound at import time in live.py (a known SDK gotcha); tests
    # set it directly on the module rather than via trigerr.set_orders_url(),
    # which would only affect a not-yet-imported copy.
    live.orders_url = "http://testserver/"


def teardown_function(_):
    lu.clear_context()


def test_place_live_order_omits_correlation_fields_when_none_available():
    with patch("trigerr.orders.live.requests.post") as mock_post:
        mock_post.return_value = _mock_response({"status": "SUCCESS"})
        live.place_live_order(credential_id="cred-1", order_details={"symbol": "INFY"})

    sent_body = mock_post.call_args.kwargs["json"]
    assert "request_id" not in sent_body
    assert "user_id" not in sent_body
    assert "strategy_id" not in sent_body
    assert sent_body["credential_id"] == "cred-1"


def test_place_live_order_uses_explicit_request_id():
    with patch("trigerr.orders.live.requests.post") as mock_post:
        mock_post.return_value = _mock_response({"status": "SUCCESS"})
        live.place_live_order(
            credential_id="cred-1", order_details={"symbol": "INFY"}, request_id="req-explicit")

    sent_body = mock_post.call_args.kwargs["json"]
    assert sent_body["request_id"] == "req-explicit"


def test_place_live_order_falls_back_to_bound_context():
    with lu.bound(request_id="req-ctx", user_id="user-9", strategy_id="strat-dummy"):
        with patch("trigerr.orders.live.requests.post") as mock_post:
            mock_post.return_value = _mock_response({"status": "SUCCESS"})
            live.place_live_order(credential_id="cred-1", order_details={"symbol": "INFY"})

    sent_body = mock_post.call_args.kwargs["json"]
    assert sent_body["request_id"] == "req-ctx"
    assert sent_body["user_id"] == "user-9"
    assert sent_body["strategy_id"] == "strat-dummy"


def test_explicit_request_id_overrides_bound_context():
    with lu.bound(request_id="req-ctx"):
        with patch("trigerr.orders.live.requests.post") as mock_post:
            mock_post.return_value = _mock_response({"status": "SUCCESS"})
            live.place_live_order(
                credential_id="cred-1", order_details={"symbol": "INFY"}, request_id="req-explicit")

    sent_body = mock_post.call_args.kwargs["json"]
    assert sent_body["request_id"] == "req-explicit"


def test_modify_live_order_carries_bound_request_id():
    with lu.bound(request_id="req-ctx"):
        with patch("trigerr.orders.live.requests.post") as mock_post:
            mock_post.return_value = _mock_response({"status": "SUCCESS"})
            live.modify_live_order(credential_id="cred-1", order_details={"order_id": "o1"})

    sent_body = mock_post.call_args.kwargs["json"]
    assert sent_body["request_id"] == "req-ctx"


def test_check_order_status_carries_bound_request_id():
    with lu.bound(request_id="req-ctx"):
        with patch("trigerr.orders.live.requests.post") as mock_post:
            mock_post.return_value = _mock_response({"status": "OPEN"})
            live.check_order_status(credential_id="cred-1", order_id="o1", exchange="NSE")

    sent_body = mock_post.call_args.kwargs["json"]
    assert sent_body["request_id"] == "req-ctx"


def test_place_live_order_still_sends_auth_headers():
    from trigerr import set_api_key
    set_api_key("test-key")
    try:
        with patch("trigerr.orders.live.requests.post") as mock_post:
            mock_post.return_value = _mock_response({"status": "SUCCESS"})
            live.place_live_order(credential_id="cred-1", order_details={"symbol": "INFY"})
        assert mock_post.call_args.kwargs["headers"] == {"x-api-key": "test-key"}
    finally:
        import trigerr
        trigerr.config["api_key"] = None


def test_validate_credential_success():
    with patch("trigerr.orders.live.requests.post") as mock_post:
        mock_post.return_value = _mock_response({"status": "SUCCESS", "message": "ok"})
        status, message = live.validate_credential(credential_id="cred-1")

    assert status == "success"
    assert message == "ok"
    sent_body = mock_post.call_args.kwargs["json"]
    assert sent_body == {"credential_id": "cred-1"}


def test_validate_credential_error():
    with patch("trigerr.orders.live.requests.post") as mock_post:
        mock_post.return_value = _mock_response({"status": "ERROR", "message": "bad credential"})
        status, message = live.validate_credential(credential_id="cred-1")

    assert status == "error"
    assert message == "bad credential"


def test_validate_credential_never_sends_credential_values():
    with patch("trigerr.orders.live.requests.post") as mock_post:
        mock_post.return_value = _mock_response({"status": "SUCCESS"})
        live.validate_credential(credential_id="cred-1")

    sent_body = mock_post.call_args.kwargs["json"]
    assert set(sent_body.keys()) == {"credential_id"}
