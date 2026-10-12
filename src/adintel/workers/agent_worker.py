"""agent-worker: consumes ``agent-runs`` and executes LangGraph runs. Holds read-only credentials only.

Graceful shutdown: on SIGTERM the current run checkpoints after its current step and the message is
returned to the queue; another worker resumes from the checkpoint (target: exit within 120 s).
"""

from __future__ import annotations

import logging
import os
import signal
import threading

from adintel.config import get_settings
from adintel.graph.engine import RunEngine
from adintel.observability.alerts import install_security_hooks
from adintel.observability.logging import configure_logging
from adintel.observability.metrics import DLQ_DEPTH, QUEUE_DEPTH, serve_metrics
from adintel.observability.tracing import configure_tracing
from adintel.queueing import AGENT_RUNS, get_queue
from adintel.storage import get_database

log = logging.getLogger("adintel.worker")


class Worker:
    def __init__(self) -> None:
        self.stop = threading.Event()
        self.queue = get_queue(AGENT_RUNS)
        self.engine = RunEngine(get_database())

    def process_one(self, wait_seconds: float = 2.0) -> bool:
        msg = self.queue.receive(wait_seconds=wait_seconds)
        if msg is None:
            return False
        body = msg.body
        try:
            result = self.engine.execute(body["tenant_id"], body["run_id"], stop=self.stop)
            if result is None and self.stop.is_set():
                self.queue.nack(msg)  # resume elsewhere from the checkpoint
            else:
                self.queue.ack(msg)
        except Exception:
            log.exception("run_crashed", extra={"run_id": body.get("run_id")})  # redelivered → DLQ after 5
        return True

    def loop(self) -> None:
        log.info("agent_worker_started")
        while not self.stop.is_set():
            QUEUE_DEPTH.labels(queue=AGENT_RUNS).set(self.queue.depth())
            DLQ_DEPTH.labels(queue=AGENT_RUNS).set(self.queue.dlq_depth())
            self.process_one()
        log.info("agent_worker_stopped")


def main() -> None:
    os.environ.setdefault("ADINTEL_PROCESS_ROLE", "worker")
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    configure_tracing("adintel-worker", s.otel_endpoint)
    install_security_hooks()
    serve_metrics(s.metrics_port)
    w = Worker()
    signal.signal(signal.SIGTERM, lambda *_: w.stop.set())
    signal.signal(signal.SIGINT, lambda *_: w.stop.set())
    w.loop()


if __name__ == "__main__":
    main()
