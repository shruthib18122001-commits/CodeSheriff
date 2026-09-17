"""
Thin entry point so `python worker.py` works from backend/ (as documented
in the README) while the actual worker lives in app/worker.py alongside
the rest of the application code.
"""
import logging

from app.worker import run_worker

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker()
