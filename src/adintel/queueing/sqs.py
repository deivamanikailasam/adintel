"""Amazon SQS queue (production). ``executions`` is a FIFO queue: the order of platform writes matters.
Redrive to a DLQ after 5 receives is configured on the queue itself (Terraform)."""

from __future__ import annotations

import json
import os
from typing import Any

from adintel.queueing.base import Message, Queue


class SqsQueue(Queue):
    def __init__(self, name: str, *, fifo: bool) -> None:
        import boto3

        self.name = name
        self.fifo = fifo
        self._sqs: Any = boto3.client("sqs")
        qname = f"adintel-{os.environ.get('ADINTEL_ENV', 'prod')}-{name}" + (".fifo" if fifo else "")
        self._url = self._sqs.get_queue_url(QueueName=qname)["QueueUrl"]
        self._dlq_url = self._sqs.get_queue_url(QueueName=qname.replace(name, f"{name}-dlq"))["QueueUrl"]

    def send(self, body: dict[str, Any], *, dedup_id: str | None = None) -> str:
        kwargs: dict[str, Any] = {"QueueUrl": self._url, "MessageBody": json.dumps(body, default=str)}
        if self.fifo:
            kwargs["MessageGroupId"] = str(body.get("tenant_id", "default"))
            kwargs["MessageDeduplicationId"] = dedup_id or str(body.get("recommendation_id"))
        return str(self._sqs.send_message(**kwargs)["MessageId"])

    def receive(self, *, wait_seconds: float = 1.0) -> Message | None:
        out = self._sqs.receive_message(QueueUrl=self._url, MaxNumberOfMessages=1,
                                        WaitTimeSeconds=int(min(20, wait_seconds)),
                                        AttributeNames=["ApproximateReceiveCount"])
        msgs = out.get("Messages", [])
        if not msgs:
            return None
        m = msgs[0]
        return Message(m["MessageId"], json.loads(m["Body"]), m["ReceiptHandle"],
                       int(m["Attributes"]["ApproximateReceiveCount"]))

    def ack(self, msg: Message) -> None:
        self._sqs.delete_message(QueueUrl=self._url, ReceiptHandle=msg.receipt)

    def nack(self, msg: Message) -> None:
        self._sqs.change_message_visibility(QueueUrl=self._url, ReceiptHandle=msg.receipt, VisibilityTimeout=0)

    def _count(self, url: str) -> int:
        a = self._sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"])
        return int(a["Attributes"]["ApproximateNumberOfMessages"])

    def depth(self) -> int:
        return self._count(self._url)

    def dlq_depth(self) -> int:
        return self._count(self._dlq_url)

    def dlq_messages(self) -> list[dict[str, Any]]:
        return []
