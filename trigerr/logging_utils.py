"""Shared structured (JSON-line) logging for Trigerr services and the SDK itself.

Stdlib-only by design: this module is imported by every trigerr-* service repo
but is also shipped in the pip-installable SDK, so it must not assume any
platform infrastructure. Where log lines end up (a file, journald, stdout) is
decided by the caller; a separate log-shipping agent (Grafana Alloy) is
responsible for getting them into centralized storage.

Usage:
    from trigerr.logging_utils import get_logger, bind, bound, redirect_stdout_to

    logger = get_logger("oms", log_file="logs/oms.jsonl")
    bind(request_id=request_id, tenant=tenant)
    logger.info("order placed", extra={"order_id": order_id})

    with bound(request_id=request_id):
        place_live_order(...)
"""
import contextvars
import json
import logging
import logging.handlers
import os
import re
import sys
from contextlib import contextmanager

# Keys that are part of the stdlib LogRecord and must not be treated as
# user-supplied `extra` fields when flattening a record to JSON.
_STD_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__.keys()) | {"message", "asctime"}

# Context fields that get their own top-level JSON key when present (kept in
# a fixed order purely for readable output; any other bound/extra key is
# still emitted, just after these).
_SCHEMA_ORDER = (
    "tenant", "service", "market", "request_id", "user_id", "strategy_id",
    "order_id", "credential_id", "idempotency_key",
)

_LOG_CTX: "contextvars.ContextVar[dict]" = contextvars.ContextVar("trigerr_log_ctx", default=None)

_loggers_configured = set()


# --------------------------------------------------------------------------
# Context propagation
# --------------------------------------------------------------------------

def bind(**ctx):
    """Merge keys into the current logging context (copy-on-write). None
    values are dropped so callers can pass optional fields unconditionally,
    e.g. bind(request_id=maybe_none)."""
    current = dict(_LOG_CTX.get() or {})
    for k, v in ctx.items():
        if v is not None:
            current[k] = v
    _LOG_CTX.set(current)


def clear_context():
    """Reset the logging context to empty. Call at the start of each unit of
    work (HTTP request, Celery task) so context never leaks across tasks
    sharing a worker/thread."""
    _LOG_CTX.set({})


def get_context():
    """Read-only copy of the current logging context."""
    return dict(_LOG_CTX.get() or {})


@contextmanager
def bound(**ctx):
    """Bind keys for the duration of a with-block, restoring the prior
    context on exit (including on exception)."""
    token_ctx = dict(_LOG_CTX.get() or {})
    bind(**ctx)
    try:
        yield
    finally:
        _LOG_CTX.set(token_ctx)


# --------------------------------------------------------------------------
# Scrubbing
# --------------------------------------------------------------------------

REDACT_KEYS = frozenset({
    "api_key", "apikey", "x_api_key", "x-api-key", "api_secret",
    "access_token", "refresh_token", "session_token", "auth_token", "token",
    "password", "passwd", "pin", "totp", "secret", "client_secret",
    "authorization", "jwt", "aws_secret_access_key", "s3_access_secret",
    "s3_secret", "private_key",
})

_REDACTED = "[REDACTED]"


def _normalize_key(key):
    return str(key).strip().lower().replace("-", "_")


def _scrub_value(value, depth):
    if depth <= 0:
        return value
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _normalize_key(k) in REDACT_KEYS:
                out[k] = _REDACTED
            else:
                out[k] = _scrub_value(v, depth - 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_scrub_value(v, depth - 1) for v in value]
    return value


# Matches key=value, 'key': 'value', "key": "value" style occurrences of a
# redacted key inside a formatted message string, e.g. an f-string dump of a
# request dict. Value is any run of non-comma/non-brace/non-quote characters,
# or a quoted string.
_MSG_KEY_PATTERN = re.compile(
    r"""(?P<prefix>['"]?\b(?:%s)\b['"]?\s*[:=]\s*)(?P<value>'[^']*'|"[^"]*"|[^,}\]\s]+)"""
    % "|".join(re.escape(k) for k in sorted(REDACT_KEYS, key=len, reverse=True)),
    re.IGNORECASE,
)


def _scrub_message(message):
    return _MSG_KEY_PATTERN.sub(lambda m: m.group("prefix") + _REDACTED, message)


class ScrubFilter(logging.Filter):
    """Redacts credential-shaped values from both the rendered message and
    any extra/context fields before a record is formatted. Defense-in-depth
    only — call sites that handle real credentials (e.g. the OMS
    BrokerContext/Secret boundary) must still avoid logging them in the
    first place."""

    def filter(self, record):
        try:
            record.msg = _scrub_message(record.getMessage())
            record.args = None
        except Exception:
            pass
        for key in list(record.__dict__.keys()):
            if key in _STD_RECORD_KEYS:
                continue
            if _normalize_key(key) in REDACT_KEYS:
                setattr(record, key, _REDACTED)
            else:
                setattr(record, key, _scrub_value(getattr(record, key), depth=4))
        return True


# --------------------------------------------------------------------------
# JSON formatting
# --------------------------------------------------------------------------

class JsonFormatter(logging.Formatter):
    def __init__(self, service):
        super().__init__()
        self.service = service

    def format(self, record):
        out = {
            "ts": self.formatTime_iso(record),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
        }
        tenant = os.environ.get("TENANT")
        if tenant:
            out["tenant"] = tenant

        out.update(get_context())

        for key, value in record.__dict__.items():
            if key in _STD_RECORD_KEYS:
                continue
            out[key] = value

        out["message"] = record.getMessage()

        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)

        return json.dumps(out, default=str)

    @staticmethod
    def formatTime_iso(record):
        import datetime
        dt = datetime.datetime.fromtimestamp(record.created, tz=datetime.timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


# --------------------------------------------------------------------------
# Logger factory
# --------------------------------------------------------------------------

def get_logger(service, log_file=None, stream=True, level=logging.INFO,
               rotate_when="midnight", backup_count=14):
    """Return a logger named `service` configured to emit JSON lines. Safe to
    call more than once for the same service — handlers are only attached
    the first time.

    log_file: path to a rotating log file (created, including parent dirs).
    stream: also emit to sys.__stderr__ (not sys.stderr — under Celery,
        stdout/stderr are wrapped by a LoggingProxy, and if this handler's
        output were itself redirected back into logging via
        redirect_stdout_to() below, writing to the wrapped stream would
        recurse infinitely).
    """
    logger = logging.getLogger(service)
    logger.setLevel(level)
    logger.propagate = False

    if service in _loggers_configured:
        return logger
    _loggers_configured.add(service)

    formatter = JsonFormatter(service)
    scrub = ScrubFilter()

    if log_file:
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_file, when=rotate_when, backupCount=backup_count, utc=True)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(scrub)
        logger.addHandler(file_handler)

    if stream:
        stream_handler = logging.StreamHandler(sys.__stderr__)
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(scrub)
        logger.addHandler(stream_handler)

    return logger


class _StdoutToLogger:
    """File-like shim: routes writes to a logger, dropping whitespace-only
    writes (print() always emits a trailing '\\n' as a separate write)."""

    def __init__(self, logger, level=logging.INFO):
        self._logger = logger
        self._level = level

    def write(self, message):
        text = message.strip()
        if text:
            self._logger.log(self._level, text)

    def flush(self):
        pass

    def isatty(self):
        # Never a real terminal; libraries that probe this before deciding
        # whether to color their output (uvicorn's default log formatter
        # does this at Config() construction time) must get a real bool,
        # not an AttributeError.
        return False


def redirect_stdout_to(logger, level=logging.INFO):
    """Route sys.stdout.write() to the given logger, so existing print()
    call sites are captured without editing them. Replaces the
    `sys.stdout.write = logger.info` pattern used previously, which also
    logged blank lines for every bare print()."""
    sys.stdout = _StdoutToLogger(logger, level=level)
