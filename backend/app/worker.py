"""
RQ worker process. Runs SEPARATELY from uvicorn -- background jobs
(repo ingestion: clone -> parse -> embed) must never execute inside a
FastAPI request handler, since a single job can take minutes and would
block the event loop / request thread if run inline.

Run with (from backend/, venv active):
    python worker.py
or:
    python -m app.worker
"""
import logging
import os
import time

from redis import Redis
from rq import Queue, Worker
from rq.timeouts import TimerDeathPenalty
from rq.worker import SimpleWorker

from app.core.config import settings
from app.services import ingestion  # noqa: F401 -- registers run_ingestion_pipeline for RQ to import by path

logger = logging.getLogger(__name__)

redis_conn = Redis.from_url(settings.redis_url)
queue = Queue("ingestion", connection=redis_conn)

# RQ's default Worker forks a child process per job (os.fork) and enforces
# job timeouts via SIGALRM, neither of which exists on Windows. SimpleWorker
# runs jobs in-process instead of forking, and TimerDeathPenalty enforces
# the timeout with a thread instead of a signal.
if os.name == "nt":
    class WorkerClass(SimpleWorker):
        death_penalty_class = TimerDeathPenalty
else:
    WorkerClass = Worker

RESTART_BACKOFF_SECONDS = 5


def run_worker() -> None:
    """
    Runs the worker forever, restarting it whenever it exits -- which
    includes RQ's own `except redis.exceptions.TimeoutError: ... break`
    inside Worker.work() (a transient Redis hiccup, e.g. an idle
    connection dropped by the OS/network, otherwise kills the worker
    permanently since RQ doesn't retry it internally).
    """
    while True:
        worker = WorkerClass([queue], connection=redis_conn)
        try:
            worker.work()
        except Exception:
            logger.exception("Worker crashed unexpectedly; restarting in %ss", RESTART_BACKOFF_SECONDS)
        else:
            logger.warning(
                "Worker exited (e.g. idle Redis timeout); restarting in %ss", RESTART_BACKOFF_SECONDS
            )
        time.sleep(RESTART_BACKOFF_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker()
