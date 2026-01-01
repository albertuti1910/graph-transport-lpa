from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.app.ports.output import IGraphRepository, IQueueService
from src.domain.models import GeoPoint, Route


@dataclass(slots=True)
class RoutingService:
    """Application service (use case) for route calculation.

    This layer orchestrates ports. Domain stays pure.
    """

    graph_repository: IGraphRepository
    queue_service: IQueueService | None = None

    def calculate_route(self, *, origin: GeoPoint, destination: GeoPoint) -> Route:
        return self.graph_repository.find_path(origin, destination)

    def enqueue_route_request(self, *, origin: GeoPoint, destination: GeoPoint) -> str:
        if self.queue_service is None:
            raise RuntimeError("Queue service not configured")

        message: Mapping[str, Any] = {
            "origin": {"lat": origin.lat, "lon": origin.lon},
            "destination": {"lat": destination.lat, "lon": destination.lon},
        }
        return self.queue_service.publish_request(message)
