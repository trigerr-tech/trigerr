import concurrent.futures
import json
import logging
import os
import threading

import pytest

from trigerr import logging_utils as lu


@pytest.fixture(autouse=True)
def _clean_context():
    lu.clear_context()
    yield
    lu.clear_context()


# --------------------------------------------------------------------------
# Context propagation
# --------------------------------------------------------------------------

def test_bind_merges_and_drops_none_values():
    lu.bind(request_id="r1", user_id=None)
    assert lu.get_context() == {"request_id": "r1"}


def test_bind_is_copy_on_write_across_calls():
    lu.bind(request_id="r1")
    ctx1 = lu.get_context()
    lu.bind(order_id="o1")
    assert ctx1 == {"request_id": "r1"}
    assert lu.get_context() == {"request_id": "r1", "order_id": "o1"}


def test_clear_context_resets():
    lu.bind(request_id="r1")
    lu.clear_context()
    assert lu.get_context() == {}


def test_bound_restores_prior_context_on_exit():
    lu.bind(request_id="outer")
    with lu.bound(request_id="inner", order_id="o1"):
        assert lu.get_context() == {"request_id": "inner", "order_id": "o1"}
    assert lu.get_context() == {"request_id": "outer"}


def test_bound_restores_on_exception():
    lu.bind(request_id="outer")
    with pytest.raises(ValueError):
        with lu.bound(request_id="inner"):
            raise ValueError("boom")
    assert lu.get_context() == {"request_id": "outer"}


def test_context_isolated_across_threads():
    seen = {}

    def worker():
        lu.bind(request_id="thread-local")
        seen["thread"] = lu.get_context()

    lu.bind(request_id="main-thread")
    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert seen["thread"] == {"request_id": "thread-local"}
    assert lu.get_context() == {"request_id": "main-thread"}


def test_context_isolated_across_thread_pool_executor():
    # Proxy for Celery prefork workers: each task should see its own bound
    # context, not one leaked from a previous task on the same worker.
    def worker(rid):
        lu.clear_context()
        lu.bind(request_id=rid)
        return lu.get_context()["request_id"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(worker, [f"r{i}" for i in range(8)]))

    assert sorted(results) == sorted(f"r{i}" for i in range(8))


# --------------------------------------------------------------------------
# Scrubbing
# --------------------------------------------------------------------------

def test_scrub_redacts_top_level_extra_key():
    record = logging.makeLogRecord({"msg": "hello", "api_key": "sk-live-123"})
    lu.ScrubFilter().filter(record)
    assert record.api_key == "[REDACTED]"


def test_scrub_redacts_nested_dict_values():
    creds = {"broker": "zerodha", "credentials": {"access_token": "abc123", "user_id": "AB1234"}}
    record = logging.makeLogRecord({"msg": "resolved", "context": creds})
    lu.ScrubFilter().filter(record)
    assert record.context["credentials"]["access_token"] == "[REDACTED]"
    assert record.context["credentials"]["user_id"] == "AB1234"
    assert record.context["broker"] == "zerodha"


def test_scrub_redacts_dicts_inside_lists():
    payload = [{"password": "hunter2"}, {"note": "ok"}]
    record = logging.makeLogRecord({"msg": "batch", "items": payload})
    lu.ScrubFilter().filter(record)
    assert record.items[0]["password"] == "[REDACTED]"
    assert record.items[1]["note"] == "ok"


def test_scrub_redacts_key_value_pairs_in_message_string():
    record = logging.makeLogRecord({"msg": "request_dict : {'api_key': 'sk-live-999', 'symbol': 'INFY'}"})
    lu.ScrubFilter().filter(record)
    rendered = record.getMessage()
    assert "sk-live-999" not in rendered
    assert "[REDACTED]" in rendered
    assert "INFY" in rendered


def test_scrub_redacts_equals_style_message_pairs():
    record = logging.makeLogRecord({"msg": "auth failed token=abcdef123456 path=/place_order"})
    lu.ScrubFilter().filter(record)
    rendered = record.getMessage()
    assert "abcdef123456" not in rendered
    assert "path=/place_order" in rendered


def test_scrub_does_not_mutate_callers_original_dict():
    creds = {"password": "hunter2"}
    record = logging.makeLogRecord({"msg": "x", "creds": creds})
    lu.ScrubFilter().filter(record)
    assert creds["password"] == "hunter2"


# --------------------------------------------------------------------------
# JSON formatting / schema
# --------------------------------------------------------------------------

def _format_one(logger, formatter, level=logging.INFO, message="hello", extra=None):
    record = logger.makeRecord(logger.name, level, __file__, 1, message, (), None, extra=extra)
    return json.loads(formatter.format(record))


def test_json_formatter_emits_required_keys():
    logger = logging.getLogger("test-schema")
    formatter = lu.JsonFormatter("oms")
    payload = _format_one(logger, formatter)
    assert payload["level"] == "INFO"
    assert payload["service"] == "oms"
    assert payload["logger"] == "test-schema"
    assert payload["message"] == "hello"
    assert payload["ts"].endswith("Z")


def test_json_formatter_omits_unset_context_keys():
    logger = logging.getLogger("test-schema-2")
    formatter = lu.JsonFormatter("oms")
    payload = _format_one(logger, formatter)
    for key in ("request_id", "order_id", "credential_id", "tenant"):
        assert key not in payload


def test_json_formatter_includes_bound_context_and_extra():
    lu.bind(request_id="r1", tenant="acme")
    logger = logging.getLogger("test-schema-3")
    formatter = lu.JsonFormatter("oms")
    payload = _format_one(logger, formatter, extra={"order_id": "o1"})
    assert payload["request_id"] == "r1"
    assert payload["tenant"] == "acme"
    assert payload["order_id"] == "o1"


def test_json_formatter_reads_tenant_from_env(monkeypatch):
    monkeypatch.setenv("TENANT", "env-tenant")
    logger = logging.getLogger("test-schema-4")
    formatter = lu.JsonFormatter("oms")
    payload = _format_one(logger, formatter)
    assert payload["tenant"] == "env-tenant"


def test_json_formatter_serializes_non_json_native_extra_values():
    class Weird:
        def __str__(self):
            return "weird-repr"

    logger = logging.getLogger("test-schema-5")
    formatter = lu.JsonFormatter("oms")
    payload = _format_one(logger, formatter, extra={"thing": Weird()})
    assert payload["thing"] == "weird-repr"


def test_json_formatter_includes_exc_info():
    logger = logging.getLogger("test-schema-6")
    formatter = lu.JsonFormatter("oms")
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record = logger.makeRecord(logger.name, logging.ERROR, __file__, 1, "failed", (), __import__("sys").exc_info())
    payload = json.loads(formatter.format(record))
    assert "RuntimeError: boom" in payload["exc"]


# --------------------------------------------------------------------------
# get_logger / handlers
# --------------------------------------------------------------------------

def test_get_logger_is_idempotent_no_duplicate_handlers(tmp_path):
    log_file = str(tmp_path / "svc.jsonl")
    logger1 = lu.get_logger("idempotent-svc", log_file=log_file, stream=False)
    handler_count = len(logger1.handlers)
    logger2 = lu.get_logger("idempotent-svc", log_file=log_file, stream=False)
    assert logger1 is logger2
    assert len(logger2.handlers) == handler_count


def test_get_logger_writes_json_lines_to_file(tmp_path):
    log_file = str(tmp_path / "svc2.jsonl")
    logger = lu.get_logger("file-svc", log_file=log_file, stream=False)
    logger.info("order placed", extra={"order_id": "o1"})
    for handler in logger.handlers:
        handler.flush()

    with open(log_file) as f:
        lines = [line for line in f.read().splitlines() if line]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["message"] == "order placed"
    assert payload["order_id"] == "o1"


def test_get_logger_creates_parent_directories(tmp_path):
    log_file = str(tmp_path / "nested" / "dir" / "svc.jsonl")
    lu.get_logger("nested-dir-svc", log_file=log_file, stream=False)
    assert os.path.isdir(os.path.dirname(log_file))


def test_get_logger_file_handler_applies_scrub_filter(tmp_path):
    log_file = str(tmp_path / "svc3.jsonl")
    logger = lu.get_logger("scrub-svc", log_file=log_file, stream=False)
    logger.info("resolved", extra={"api_key": "sk-live-123"})
    for handler in logger.handlers:
        handler.flush()

    with open(log_file) as f:
        content = f.read()
    assert "sk-live-123" not in content
    assert "[REDACTED]" in content


# --------------------------------------------------------------------------
# stdout redirection
# --------------------------------------------------------------------------

def test_redirect_stdout_to_logs_print_output(monkeypatch, tmp_path):
    log_file = str(tmp_path / "stdout.jsonl")
    logger = lu.get_logger("stdout-svc", log_file=log_file, stream=False)

    import sys
    original_stdout = sys.stdout
    try:
        lu.redirect_stdout_to(logger)
        print("hello from print")
    finally:
        sys.stdout = original_stdout

    for handler in logger.handlers:
        handler.flush()
    with open(log_file) as f:
        lines = [line for line in f.read().splitlines() if line]
    assert any(json.loads(line)["message"] == "hello from print" for line in lines)


def test_redirect_stdout_to_shim_supports_isatty(tmp_path):
    # Real regression: uvicorn's default log formatter calls
    # sys.stdout.isatty() at Config() construction time to decide whether to
    # color output; a plain object without this method raises AttributeError
    # and uvicorn fails to start under redirect_stdout_to().
    log_file = str(tmp_path / "isatty.jsonl")
    logger = lu.get_logger("isatty-svc", log_file=log_file, stream=False)

    import sys
    original_stdout = sys.stdout
    try:
        lu.redirect_stdout_to(logger)
        assert sys.stdout.isatty() is False
    finally:
        sys.stdout = original_stdout


def test_redirect_stdout_to_drops_whitespace_only_writes(tmp_path):
    log_file = str(tmp_path / "stdout2.jsonl")
    logger = lu.get_logger("stdout-svc-2", log_file=log_file, stream=False)

    import sys
    original_stdout = sys.stdout
    try:
        lu.redirect_stdout_to(logger)
        print()
        print("real message")
    finally:
        sys.stdout = original_stdout

    for handler in logger.handlers:
        handler.flush()
    with open(log_file) as f:
        lines = [line for line in f.read().splitlines() if line]
    assert len(lines) == 1
    assert json.loads(lines[0])["message"] == "real message"
