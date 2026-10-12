"""Work queues: ``agent-runs`` (visibility timeout = run budget) and ``executions`` (FIFO)."""

from adintel.queueing.base import Message, Queue, get_queue, reset_queues

AGENT_RUNS = "agent-runs"
EXECUTIONS = "executions"
VISIBILITY = {AGENT_RUNS: 900.0, EXECUTIONS: 120.0}
MAX_RECEIVES = 5

__all__ = ["AGENT_RUNS", "EXECUTIONS", "MAX_RECEIVES", "VISIBILITY", "Message", "Queue", "get_queue", "reset_queues"]
