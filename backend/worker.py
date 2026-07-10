"""
Thin entry point so `python worker.py` works from backend/ (as documented
in the README) while the actual worker lives in app/worker.py alongside
the rest of the application code.
"""
from app.worker import queue, redis_conn  # noqa: F401
from rq import Worker

if __name__ == "__main__":
    Worker([queue], connection=redis_conn).work()
