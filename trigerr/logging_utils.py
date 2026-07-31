"""Shared structured (JSON-line) logging for Trigerr services and the SDK itself.

Kept byte-identical to project-sysstra's sysstra_logging/logging_utils.py
apart from this docstring and the contextvar names: both projects push into
one Loki, so a query written against one has to work against the other. The
schema half of that is pinned by tests/fixtures/envelope.golden.json, which
is the same file in both repos — a drift in either fails that repo's tests.
(An earlier "keep the two in sync" comment did not survive contact with
reality; the fixture is the enforcement.)

Stdlib-only by design: this module is imported by every trigerr-* service repo
but is also shipped in the pip-installable SDK, so it must not assume any
platform infrastructure. Where log lines end up (a file, journald, stdout) is
decided by the caller; a separate log-shipping agent (Grafana Alloy) is
responsible for getting them into centralized storage.

Every line carries the same identity block (IDENTITY_FIELDS) in the same
order, blank where unknown, so a consumer can group by repo, host, market or
environment without knowing which service wrote the line. Domain fields
(request_id, mode, segment, job, ...) appear only on the repos that have
those concepts — see _DOMAIN_ORDER.

Usage:
    from trigerr.logging_utils import get_logger, bind, bound, clear_context

    logger = get_logger("oms", log_file="logs/oms.jsonl",
                        service="trigerr-oms")
    bind(request_id=request_id, tenant=tenant)
    logger.info("order placed", extra={"order_id": order_id})

    with bound(request_id=request_id):
        place_live_order(...)

`service` names the repo and is passed by each repo's create_logger from its
own SERVICE constant; `name` is the per-script or per-request logger name and
appears as `logger`. Set LOG_FORMAT=text for a human-readable formatter
during local development / tailing; the default is single-line JSON.
"""
import contextvars
import json
import logging
import logging.handlers
import os
import re
import socket
import sys
from contextlib import contextmanager

# Keys that are part of the stdlib LogRecord and must not be treated as
# user-supplied `extra` fields when flattening a record to JSON.
_STD_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__.keys()) | {"message", "asctime"}

# Bumped when IDENTITY_FIELDS changes. Emitted on every line so a format
# change stays detectable across a fleet that is mid-rollout — repos and
# instances pick up a new SDK at different times, and without this a query
# cannot tell a line that predates the change from one that lost a field.
SCHEMA_VERSION = "1"

# The identity block: emitted on EVERY line, in this order, blank when
# unknown. These answer "which repo, which part of it, which host, which
# market, which environment, and what kind of line" — everything needed to
# find and group logs without knowing in advance which repo wrote them. A
# blank here means misconfigured, not "not applicable": every one of these
# applies to every process.
#
# event/status are padded despite being blank on most lines because they are
# the operational vocabulary — with them guaranteed present, one dashboard
# panel works unchanged against every service.
IDENTITY_FIELDS = (
    "ts", "level", "schema", "service", "component", "env", "host",
    "tenant", "market", "event", "status", "logger", "message",
)

# Computed from the record itself; never overridable by bind()/extra=.
_INTRINSIC_FIELDS = frozenset({"ts", "level", "schema", "logger", "message"})

# Distinguishes "key absent" from "key present with a falsy value" when
# resolving a field: bind(market="") must win over MARKET=IN, the same way
# bind(market="IN") does.
_MISSING = object()

# Identity fields that fall back to an environment variable before their
# blank default. bind()/extra= still win over the environment — a per-request
# bind(market="IN") must beat a process-wide MARKET=US.
_ENV_FIELDS = {
    "service": "SERVICE",
    "env": "ENVIRONMENT",
    "host": "HOSTNAME",
    "tenant": "TENANT",
    "market": "MARKET",
}

# Every deployment that ships logs is production; dev is the exception and
# generally runs LOG_FORMAT=text without shipping at all. Defaulting to ""
# instead would leave the field blank on every host forever, which is worse
# than a wrong-but-visible value.
_DEFAULT_ENV = "prod"

# Domain fields: reserved names with fixed meanings, emitted ONLY when the
# call site supplies them. Deliberately not blank-padded — a `request_id: ""`
# on a data-collection line would be indistinguishable from a trading line
# that failed to populate one, and data collection has no such concept at
# all. Ordered here purely so output stays readable; anything not listed is
# still emitted, just afterwards.
_DOMAIN_ORDER = (
    # Trading: trading-strategies, backtesting-strategies, orders-api,
    # brokers-automation. request_id is the Mongo {mode}_requests._id and is
    # never generated — batch work uses run_id below, so a query for one can
    # never pick up the other.
    "request_id", "mode", "strategy", "strategy_id", "user_id",
    "order_id", "broker", "credential_id", "idempotency_key",
    # Data collection.
    "segment", "session", "symbol",
    # Batch jobs (see jobs.job_run).
    "job", "run_id", "duration_s",
    # Long-running processes (see health.HealthReporter).
    "pid", "uptime_s",
    "exc",
)

_LOG_CTX: "contextvars.ContextVar[dict]" = contextvars.ContextVar("trigerr_log_ctx", default=None)
_CURRENT_LOGGER: "contextvars.ContextVar[logging.Logger]" = contextvars.ContextVar("trigerr_current_logger", default=None)

_loggers_configured = set()


def get_current_logger():
    """Returns the logger most recently passed to redirect_stdout_to() in
    this context, or None if none has been set yet. Lets shared helper
    modules that receive no logger argument (e.g. sts_common.py, called from
    many different per-request scripts) still log at the correct level and
    with structured extra= fields into whichever logger the caller is
    currently using, instead of only being able to print()."""
    return _CURRENT_LOGGER.get()


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
    work (Celery task, HTTP request) so context never leaks across tasks
    sharing a worker/thread — critical for `mode` (paper vs. real-money),
    which must never bleed from one request's log lines into another's."""
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
    "access_token", "refresh_token", "session_token", "session_token_key",
    "auth_token", "token", "request_token",
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
    only — call sites that handle real credentials must still avoid logging
    them in the first place."""

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
# Formatting
# --------------------------------------------------------------------------

def _format_time_iso(record):
    import datetime
    dt = datetime.datetime.fromtimestamp(record.created, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


class JsonFormatter(logging.Formatter):
    """Renders a record as the identity block (always, in a fixed order,
    blank when unknown) followed by whatever domain fields the call site
    supplied.

    The identity block is what makes one Alloy config and one dashboard
    panel work across every repo: a consumer can rely on those keys being
    present without knowing which service wrote the line. Domain fields are
    not padded — see _DOMAIN_ORDER."""

    def __init__(self, service, defaults=None):
        super().__init__()
        self.service = service
        # Per-logger identity values, e.g. {"segment": "options",
        # "component": "stream_ticks.py"}. Held on the formatter rather than
        # bound into the context on purpose: a new thread starts with an
        # EMPTY contextvar context, and the data-collection repos run their
        # tick handlers and processor workers on their own threads — a
        # bind() in the main thread would silently vanish from exactly the
        # lines that carry the data. A formatter attribute is read-only and
        # shared, so every thread sees it.
        self.defaults = dict(defaults or {})

    def _identity_default(self, field, record):
        if field == "ts":
            return _format_time_iso(record)
        if field == "level":
            return record.levelname
        if field == "schema":
            return SCHEMA_VERSION
        if field == "logger":
            return record.name
        if field == "message":
            return record.getMessage()
        # Below extra=/bind() (a per-line value must still win) but above the
        # environment: a per-logger default is more specific than a
        # process-wide env var.
        if field in self.defaults:
            return self.defaults[field]
        if field == "service":
            # The constructor argument is the fallback, not the authority:
            # bind(service=...) and SERVICE both outrank it, handled by the
            # precedence chain in format().
            return self.service or ""
        if field == "host":
            # HOSTNAME is a shell variable and is frequently not exported to
            # a Python process, so falling back to the env var alone would
            # leave this blank on most hosts.
            return os.environ.get("HOSTNAME") or socket.gethostname()
        if field == "env":
            return os.environ.get("ENVIRONMENT") or _DEFAULT_ENV
        env_var = _ENV_FIELDS.get(field)
        if env_var:
            return os.environ.get(env_var) or ""
        return ""

    def format(self, record):
        ctx = get_context()
        extras = {k: v for k, v in record.__dict__.items() if k not in _STD_RECORD_KEYS}

        out = {}
        for field in IDENTITY_FIELDS:
            # Consume the key from BOTH sources whichever one wins: the tail
            # below is built from what's left, and a leftover copy there
            # would overwrite the identity value via out.update(remaining)
            # — silently reinstating a stale bound field over the extra=
            # that was meant to override it for this one line.
            from_extras = extras.pop(field, _MISSING)
            from_ctx = ctx.pop(field, _MISSING)

            if field in _INTRINSIC_FIELDS:
                # Computed from the record; a call site cannot displace it.
                # (stdlib already rejects extra={"message"/"asctime": ...},
                # but "level", "logger" and "ts" are not names it guards.)
                out[field] = self._identity_default(field, record)
            elif from_extras is not _MISSING:
                out[field] = from_extras
            elif from_ctx is not _MISSING:
                out[field] = from_ctx
            else:
                out[field] = self._identity_default(field, record)

        if record.exc_info:
            extras["exc"] = self.formatException(record.exc_info)

        remaining = dict(ctx)
        remaining.update(extras)

        # Formatter defaults for non-identity fields (segment, ...). Blank
        # ones are skipped rather than emitted: domain fields are never
        # padded, so a top-level script with no segment must have no segment
        # key at all, not segment="".
        for key, value in self.defaults.items():
            if key not in out and key not in remaining and value not in ("", None):
                remaining[key] = value

        for field in _DOMAIN_ORDER:
            if field in remaining:
                out[field] = remaining.pop(field)

        # Free-form tail: anything the call site passed that isn't a reserved
        # name. Emitted unchanged so per-strategy payloads keep working.
        out.update(remaining)

        return json.dumps(out, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable formatter for local dev / `tail -f` — selected via
    LOG_FORMAT=text. Bound context (request_id, mode, strategy, ...) is
    appended so it stays visible without parsing JSON."""

    def __init__(self):
        super().__init__(fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
                         datefmt="%Y-%m-%d %H:%M:%S")

    def format(self, record):
        base = super().format(record)
        ctx = get_context()
        if ctx:
            ctx_str = " ".join(f"{k}={v}" for k, v in ctx.items())
            base = f"{base}  [{ctx_str}]"
        if record.exc_info:
            base = f"{base}\n{self.formatException(record.exc_info)}"
        return base


def _make_formatter(service, defaults=None):
    if os.environ.get("LOG_FORMAT", "json").lower() == "text":
        return TextFormatter()
    return JsonFormatter(service, defaults=defaults)


# --------------------------------------------------------------------------
# Logger factory
# --------------------------------------------------------------------------

def get_logger(name=None, log_file=None, stream=True, level=logging.INFO,
               rotate_when="midnight", backup_count=14, service=None,
               defaults=None):
    """Return a logger named `name` configured to emit structured log lines.
    Safe to call more than once for the same name — handlers are only
    attached the first time.

    name: the logger name, which appears as `logger` on every line. Callers
        pass a per-script or per-request value here (e.g.
        "syss_sha_eod-vt-<request_id>"). Defaults to `service` so the
        pre-split call style — get_logger(service="oms", ...), used across
        project-trigerr — keeps working unchanged.
    service: which repo the line came from, e.g. "trigerr-data-collection".
        Falls back to the SERVICE environment variable, then to `name`.
        These were previously the same argument, so every line reported a
        per-request logger name as its service and no query could group by
        repo; each repo's create_logger now passes its own SERVICE constant.
    defaults: identity fields every line from this logger should carry, e.g.
        {"segment": "options", "component": "stream_ticks.py"}. Use this
        rather than bind() for values fixed at logger-creation time in a
        process that spawns threads: a new thread starts with an empty
        contextvar context, so a bind() in the main thread never reaches the
        worker that does the logging.
    log_file: path to a rotating log file (created, including parent dirs).
    stream: also emit to sys.__stderr__ (not sys.stderr — under Celery,
        stdout/stderr are wrapped by a LoggingProxy, and if this handler's
        output were itself redirected back into logging via
        redirect_stdout_to() below, writing to the wrapped stream would
        recurse infinitely).
    """
    name = name or service
    if not name:
        raise TypeError("get_logger() needs a name (or a service to name the logger after)")

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if name in _loggers_configured:
        return logger
    _loggers_configured.add(name)

    formatter = _make_formatter(service or os.environ.get("SERVICE") or name,
                                defaults=defaults)
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
        # whether to color their output must get a real bool, not an
        # AttributeError.
        return False


def redirect_stdout_to(logger, level=logging.INFO):
    """Route sys.stdout.write() to the given logger, so existing print()
    call sites are captured without editing them. Replaces the
    `sys.stdout.write = logger.info` pattern used previously, which also
    logged a blank record for every bare print()'s trailing newline."""
    sys.stdout = _StdoutToLogger(logger, level=level)
    _CURRENT_LOGGER.set(logger)
