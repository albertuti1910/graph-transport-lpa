from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping

from botocore.exceptions import ClientError

from src.adapters.aws import sqs_client
from src.app.ports.output import IQueueService


@dataclass(slots=True)
class SQSQueueAdapter(IQueueService):
    """SQS adapter (supports LocalStack via env).

    Env vars:
      - SQS_QUEUE_URL
            - ENDPOINT_URL (preferred for LocalStack)
            - USE_LOCALSTACK, LOCALSTACK_ENDPOINT_URL, AWS_REGION (legacy)
    """

    queue_url: str | None = None

    def _queue_url(self) -> str:
        value = self.queue_url or os.getenv("SQS_QUEUE_URL")
        if not value:
            raise RuntimeError("Missing SQS_QUEUE_URL")
        return value

    def publish_request(self, message: Mapping[str, Any]) -> str:
        sqs = sqs_client()
        resp = sqs.send_message(
            QueueUrl=self._queue_url(), MessageBody=json.dumps(dict(message))
        )
        return str(resp.get("MessageId", ""))

    def consume_request(
        self, *, max_messages: int = 1, wait_time_s: int = 10
    ) -> list[Mapping[str, Any]]:
        sqs = sqs_client()

        try:
            resp = sqs.receive_message(
                QueueUrl=self._queue_url(),
                MaxNumberOfMessages=max(1, min(10, int(max_messages))),
                WaitTimeSeconds=max(0, min(20, int(wait_time_s))),
            )
        except ClientError as exc:
            # LocalStack race: worker may start polling before init script creates the queue.
            code = (
                exc.response.get("Error", {}).get("Code")
                if isinstance(getattr(exc, "response", None), dict)
                else None
            )
            if code in {"AWS.SimpleQueueService.NonExistentQueue", "QueueDoesNotExist"}:
                return []
            raise

        messages = resp.get("Messages", []) or []
        bodies: list[Mapping[str, Any]] = []

        for msg in messages:
            raw_body = msg.get("Body")
            if raw_body is None:
                continue

            try:
                decoded = json.loads(raw_body)
            except json.JSONDecodeError:
                decoded = {"raw": raw_body}

            bodies.append(decoded)

            receipt = msg.get("ReceiptHandle")
            if receipt:
                sqs.delete_message(QueueUrl=self._queue_url(), ReceiptHandle=receipt)

        return bodies
