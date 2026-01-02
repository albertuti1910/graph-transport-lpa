from __future__ import annotations

import os
import time
from uuid import uuid4

import networkx as nx
import pytest

from src.adapters.aws import dynamodb_client, s3_client, sqs_client
from src.adapters.maps.s3_cached_map_adapter import S3CachedMapAdapter
from src.adapters.messaging.sqs_queue_adapter import SQSQueueAdapter
from src.adapters.persistence.dynamodb_route_result_repository import (
    DynamoDbRouteResultRepository,
)
from src.domain.models.geo import GeoPoint


@pytest.mark.integration
def test_sqs_queue_adapter_publish_and_consume(require_localstack: str) -> None:
    sqs = sqs_client()

    queue_name = "urbanpath-test-queue"
    queue_url = sqs.create_queue(QueueName=queue_name)["QueueUrl"]
    os.environ["SQS_QUEUE_URL"] = queue_url

    adapter = SQSQueueAdapter()
    message = {"hello": "world", "n": 1}
    msg_id = adapter.publish_request(message)
    assert msg_id

    # Retry a bit to account for async delivery.
    deadline = time.time() + 5.0
    received: list[dict] = []
    while time.time() < deadline and not received:
        received = [
            dict(m) for m in adapter.consume_request(max_messages=1, wait_time_s=1)
        ]
        if not received:
            time.sleep(0.1)

    assert received
    assert received[0]["hello"] == "world"
    assert received[0]["n"] == 1


@pytest.mark.integration
def test_dynamodb_route_result_repository_put_and_get(require_localstack: str) -> None:
    table = "urbanpath-test-route-results"
    os.environ["DDB_TABLE"] = table

    ddb = dynamodb_client()

    # Create table if needed.
    existing = ddb.list_tables().get("TableNames", [])
    if table not in existing:
        ddb.create_table(
            TableName=table,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "request_id", "AttributeType": "S"}
            ],
            KeySchema=[{"AttributeName": "request_id", "KeyType": "HASH"}],
        )

        waiter = ddb.get_waiter("table_exists")
        waiter.wait(TableName=table)

    repo = DynamoDbRouteResultRepository()
    repo.put_pending(request_id="req-1", payload={"a": 1})
    repo.put_success(request_id="req-1", result={"ok": True})

    got = repo.get(request_id="req-1")
    assert got is not None
    assert got["request_id"] == "req-1"
    assert got["status"] == "SUCCESS"
    assert got["payload"]["a"] == 1
    assert got["result"]["ok"] is True


@pytest.mark.integration
def test_s3_cached_map_adapter_caches_graph(require_localstack: str) -> None:
    bucket = "urbanpath-test-street-graphs"
    os.environ["STREET_GRAPH_BUCKET"] = bucket
    os.environ["STREET_GRAPH_PREFIX"] = f"street-graphs-test-{uuid4()}"

    s3 = s3_client()
    try:
        s3.create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={
                "LocationConstraint": os.environ.get("AWS_REGION", "eu-west-1")
            },
        )
    except Exception:
        pass

    class _FakeUpstream:
        network_type = "walk"

        def __init__(self) -> None:
            self.calls = 0

        def get_street_graph(self, *, center: GeoPoint, dist_m: int):
            self.calls += 1
            g = nx.Graph()
            g.add_node("a", x=center.lon, y=center.lat)
            return g

    upstream = _FakeUpstream()
    cached = S3CachedMapAdapter(upstream=upstream)

    center = GeoPoint(lat=28.12, lon=-15.43)
    g1 = cached.get_street_graph(center=center, dist_m=1234)
    assert upstream.calls == 1
    assert "a" in g1

    # Second call should come from cache; simulate upstream failure.
    def _boom(*args, **kwargs):
        raise RuntimeError("should not be called")

    upstream.get_street_graph = _boom  # type: ignore[assignment]
    g2 = cached.get_street_graph(center=center, dist_m=1234)
    assert "a" in g2
