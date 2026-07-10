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
from redis import Redis
from rq import Queue, Worker

from app.core.config import settings
from app.services import ingestion  # noqa: F401 -- registers run_ingestion_pipeline for RQ to import by path

redis_conn = Redis.from_url(settings.redis_url)
queue = Queue("ingestion", connection=redis_conn)

if __name__ == "__main__":
    worker = Worker([queue], connection=redis_conn)
    worker.work()
