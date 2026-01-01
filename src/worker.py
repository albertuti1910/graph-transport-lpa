from __future__ import annotations

import os
import time
from datetime import datetime

from src.adapters.maps.osmnx_map_adapter import OSMnxMapAdapter
from src.adapters.maps.s3_cached_map_adapter import S3CachedMapAdapter
from src.adapters.messaging.sqs_queue_adapter import SQSQueueAdapter
from src.adapters.persistence.dynamodb_route_result_repository import (
    DynamoDbRouteResultRepository,
)
from src.adapters.persistence.local_gtfs_repository import LocalGtfsRepository
from src.app.ports.output import IMapProvider
from src.app.services.multimodal_routing_service import MultimodalRoutingService
from src.domain.models import GeoPoint


def _route_to_dict(route) -> dict:
    return {
        "origin": {"lat": route.origin.lat, "lon": route.origin.lon},
        "destination": {"lat": route.destination.lat, "lon": route.destination.lon},
        "legs": [
            {
                "mode": leg.mode.value,
                "origin": {"lat": leg.origin.lat, "lon": leg.origin.lon},
                "destination": {"lat": leg.destination.lat, "lon": leg.destination.lon},
                "distance_m": leg.distance_m,
                "duration_s": leg.duration_s,
                "path": (
                    [{"lat": p.lat, "lon": p.lon} for p in getattr(leg, "path", ())]
                    if getattr(leg, "path", None)
                    else None
                ),
                "line": (
                    {
                        "route_id": leg.line.route_id,
                        "short_name": leg.line.short_name,
                        "long_name": leg.line.long_name,
                        "color": leg.line.color,
                        "text_color": leg.line.text_color,
                    }
                    if getattr(leg, "line", None)
                    else None
                ),
                "trip_id": getattr(leg, "trip_id", None),
            }
            for leg in route.legs
        ],
        "total_distance_m": route.total_distance_m,
        "total_duration_s": route.total_duration_s,
    }


def main() -> None:
    queue = SQSQueueAdapter()
    results = DynamoDbRouteResultRepository()

    base_provider: IMapProvider = OSMnxMapAdapter(network_type="walk")
    map_provider: IMapProvider = base_provider
    if os.getenv("STREET_GRAPH_BUCKET"):
        map_provider = S3CachedMapAdapter(upstream=base_provider)

    router = MultimodalRoutingService(
        gtfs_repository=LocalGtfsRepository(),
        map_provider=map_provider,
        queue_service=None,
    )

    loop = os.getenv("WORKER_LOOP", "1").strip().lower() not in {"0", "false", "no"}

    while True:
        messages = queue.consume_request(max_messages=5, wait_time_s=10)
        if not messages:
            if not loop:
                return
            time.sleep(0.2)
            continue

        for msg in messages:
            try:
                request_id = str(msg.get("request_id") or "")
                if not request_id:
                    continue

                origin = msg.get("origin") or {}
                destination = msg.get("destination") or {}
                depart_at_raw = msg.get("depart_at")
                preference = msg.get("preference", "fastest")

                depart_at = (
                    datetime.fromisoformat(depart_at_raw)
                    if isinstance(depart_at_raw, str)
                    else datetime.now()
                )

                route = router.calculate_route(
                    origin=GeoPoint(lat=float(origin["lat"]), lon=float(origin["lon"])),
                    destination=GeoPoint(
                        lat=float(destination["lat"]), lon=float(destination["lon"])
                    ),
                    depart_at=depart_at,
                    preference=preference,
                )

                results.put_success(request_id=request_id, result=_route_to_dict(route))
            except Exception as exc:
                # Best-effort: record error; message already deleted by adapter.
                try:
                    rid = str(msg.get("request_id") or "")
                    if rid:
                        results.put_error(
                            request_id=rid, error=f"{type(exc).__name__}: {exc}"
                        )
                except Exception:
                    pass


if __name__ == "__main__":
    main()
