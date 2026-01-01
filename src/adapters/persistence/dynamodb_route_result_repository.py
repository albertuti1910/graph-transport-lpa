from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping

from src.adapters.aws import dynamodb_client
from src.app.ports.output import IRouteResultRepository


@dataclass(slots=True)
class DynamoDbRouteResultRepository(IRouteResultRepository):
    """Stores routing job status and results in DynamoDB.

    Env vars:
      - DDB_TABLE (default: urbanpath-route-results)
      - ENDPOINT_URL (preferred for LocalStack)
      - AWS_REGION
    """

    table_name: str | None = None

    def _table(self) -> str:
        return self.table_name or os.getenv("DDB_TABLE") or "urbanpath-route-results"

    def put_pending(self, *, request_id: str, payload: Mapping[str, Any]) -> None:
        now_ms = int(time.time() * 1000)
        ddb = dynamodb_client()
        ddb.put_item(
            TableName=self._table(),
            Item={
                "request_id": {"S": request_id},
                "status": {"S": "PENDING"},
                "created_at_ms": {"N": str(now_ms)},
                "updated_at_ms": {"N": str(now_ms)},
                "payload": {"S": json.dumps(dict(payload))},
            },
        )

    def put_success(self, *, request_id: str, result: Mapping[str, Any]) -> None:
        now_ms = int(time.time() * 1000)
        ddb = dynamodb_client()
        ddb.update_item(
            TableName=self._table(),
            Key={"request_id": {"S": request_id}},
            UpdateExpression="SET #s = :s, updated_at_ms = :u, #r = :r REMOVE #e",
            ExpressionAttributeNames={"#s": "status", "#r": "result", "#e": "error"},
            ExpressionAttributeValues={
                ":s": {"S": "SUCCESS"},
                ":u": {"N": str(now_ms)},
                ":r": {"S": json.dumps(dict(result))},
            },
        )

    def put_error(self, *, request_id: str, error: str) -> None:
        now_ms = int(time.time() * 1000)
        ddb = dynamodb_client()
        ddb.update_item(
            TableName=self._table(),
            Key={"request_id": {"S": request_id}},
            UpdateExpression="SET #s = :s, updated_at_ms = :u, #e = :e",
            ExpressionAttributeNames={"#s": "status", "#e": "error"},
            ExpressionAttributeValues={
                ":s": {"S": "ERROR"},
                ":u": {"N": str(now_ms)},
                ":e": {"S": error[:4000]},
            },
        )

    def get(self, *, request_id: str) -> Mapping[str, Any] | None:
        ddb = dynamodb_client()
        resp = ddb.get_item(
            TableName=self._table(),
            Key={"request_id": {"S": request_id}},
            ConsistentRead=True,
        )
        item = resp.get("Item")
        if not item:
            return None

        out: dict[str, Any] = {
            "request_id": item["request_id"]["S"],
            "status": item.get("status", {}).get("S"),
            "created_at_ms": int(item.get("created_at_ms", {}).get("N", "0")),
            "updated_at_ms": int(item.get("updated_at_ms", {}).get("N", "0")),
        }
        if "payload" in item and "S" in item["payload"]:
            out["payload"] = json.loads(item["payload"]["S"])
        if "result" in item and "S" in item["result"]:
            out["result"] = json.loads(item["result"]["S"])
        if "error" in item and "S" in item["error"]:
            out["error"] = item["error"]["S"]
        return out
