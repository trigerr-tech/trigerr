"""Lifecycle events for batch work — cron jobs, screeners, db/S3 syncs.

Promotes a pattern that was hand-rolled identically in every batch script
(job_start / job_complete / job_failed emitted around a try/except, e.g.
trigerr-data-collection-in/stocks/stocks_daily_eod.py). Doing it
in one place means every job emits the same three events with the same field
names, so "did last night's sync run, and how long did it take" is one query
regardless of which repo owns the job.

Usage:
    from trigerr import get_logger, job_run

    logger = get_logger("s3_sync", log_file=..., service="trigerr-data-collection-in")

    with job_run(logger, "s3_sync"):
        sync_bucket()

A failure re-raises after logging, so a cron job still exits non-zero and
whatever supervises it still sees the failure.
"""
import time
import uuid
from contextlib import contextmanager

from trigerr_logging import bound


def new_run_id():
    """Short, time-ordered id for one execution of a batch job.

    Deliberately not called request_id: that name is the Mongo
    {mode}_requests._id in the trading repos and is never generated. Keeping
    the two names distinct means a query for one can never pick up the
    other."""
    return f"{int(time.time())}-{uuid.uuid4().hex[:8]}"


@contextmanager
def job_run(logger, job, run_id=None, **ctx):
    """Emit job_start / job_complete / job_failed around a batch job.

    Binds `job` and `run_id` for the duration so every line the job logs in
    between carries them too — without that, the start and end events are
    correlated but everything the job actually did is not.

    Restores the prior context on exit (including on failure) so a script
    running several jobs in sequence doesn't leak one job's id into the
    next."""
    run_id = run_id or new_run_id()

    with bound(job=job, run_id=run_id, **ctx):
        started = time.monotonic()
        logger.info(f"job started: {job}", extra={"event": "job_start"})

        try:
            yield run_id
        except BaseException as exc:
            # BaseException, not Exception: a job killed by SIGTERM (how
            # these are usually stopped) raises SystemExit/KeyboardInterrupt,
            # and those runs would otherwise leave a job_start with no
            # terminal event — indistinguishable from a job still running.
            logger.exception(f"job failed: {job}", extra={
                "event": "job_failed",
                "status": "failed",
                "duration_s": round(time.monotonic() - started, 3),
                "reason": type(exc).__name__,
            })
            raise
        else:
            logger.info(f"job complete: {job}", extra={
                "event": "job_complete",
                "status": "ok",
                "duration_s": round(time.monotonic() - started, 3),
            })
