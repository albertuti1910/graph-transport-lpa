from __future__ import annotations

import os

from src.adapters.maps.osmnx_map_adapter import OSMnxMapAdapter
from src.adapters.maps.s3_cached_map_adapter import S3CachedMapAdapter
from src.adapters.messaging.sqs_queue_adapter import SQSQueueAdapter
from src.adapters.persistence.dynamodb_route_result_repository import (
    DynamoDbRouteResultRepository,
)
from src.adapters.persistence.local_gtfs_repository import LocalGtfsRepository
from src.app.ports.output import IMapProvider
from src.app.services.multimodal_routing_service import MultimodalRoutingService
from src.app.services.route_jobs_service import RouteJobsService


def get_routing_service() -> MultimodalRoutingService:
    gtfs_repo = LocalGtfsRepository()
    base_provider: IMapProvider = OSMnxMapAdapter(network_type="walk")
    map_provider: IMapProvider = base_provider
    if os.getenv("STREET_GRAPH_BUCKET"):
        map_provider = S3CachedMapAdapter(upstream=base_provider)

    queue_service = None
    if os.getenv("SQS_QUEUE_URL"):
        queue_service = SQSQueueAdapter()

    service = MultimodalRoutingService(
        gtfs_repository=gtfs_repo,
        map_provider=map_provider,
        queue_service=queue_service,
    )

    # Allow tuning via env without changing code.
    if os.getenv("STREET_GRAPH_DIST_M"):
        service.street_graph_dist_m = int(os.environ["STREET_GRAPH_DIST_M"])
    if os.getenv("CANDIDATE_RADIUS_M"):
        service.candidate_radius_m = float(os.environ["CANDIDATE_RADIUS_M"])
    if os.getenv("MAX_CANDIDATE_STOPS"):
        service.max_candidate_stops = int(os.environ["MAX_CANDIDATE_STOPS"])

    return service


def get_route_jobs_service() -> RouteJobsService:
    if not os.getenv("SQS_QUEUE_URL"):
        raise RuntimeError("Queue service not configured")

    queue = SQSQueueAdapter()
    results = DynamoDbRouteResultRepository()
    return RouteJobsService(queue_service=queue, result_repository=results)
