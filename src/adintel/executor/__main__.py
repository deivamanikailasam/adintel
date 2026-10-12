"""``python -m adintel.executor`` — consume the executions FIFO queue. No model access in this process."""

from __future__ import annotations

import logging
import os
import signal
import threading

os.environ.setdefault("ADINTEL_PROCESS_ROLE", "executor")

from adintel.config import get_settings
from adintel.executor.service import Executor
from adintel.observability.logging import configure_logging
from adintel.observability.metrics import DLQ_DEPTH, QUEUE_DEPTH, serve_metrics
from adintel.queueing import EXECUTIONS, get_queue
from adintel.storage import get_database

log = logging.getLogger("adintel.executor")


def main() -> None:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    serve_metrics(s.metrics_port + 1)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    q = get_queue(EXECUTIONS)
    db = get_database()
    log.info("executor_started", extra={"queue": EXECUTIONS})
    while not stop.is_set():
        QUEUE_DEPTH.labels(queue=EXECUTIONS).set(q.depth())
        DLQ_DEPTH.labels(queue=EXECUTIONS).set(q.dlq_depth())
        msg = q.receive(wait_seconds=2)
        if msg is None:
            continue
        body = msg.body
        try:
            out = Executor(db, body["tenant_id"]).execute(body["recommendation_id"], body["approval_id"])
            log.info("execution_processed", extra={"recommendation_id": body["recommendation_id"], **out})
            q.ack(msg)  # refused and failed executions are final: never auto-retried
        except Exception:
            log.exception("execution_crashed")  # message becomes visible again → DLQ after 5 receives
    log.info("executor_stopped")


if __name__ == "__main__":
    main()
