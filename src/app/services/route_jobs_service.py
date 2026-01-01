from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from uuid import uuid4

from src.app.ports.output import IQueueService, IRouteResultRepository
from src.app.services.multimodal_routing_service import Preference
from src.domain.models import GeoPoint


@dataclass(slots=True)
class RouteJobsService:
    queue_service: IQueueService
    result_repository: IRouteResultRepository

    def submit(
        self,
        *,
        origin: GeoPoint,
        destination: GeoPoint,
        depart_at: datetime,
        preference: Preference,
    ) -> str:
        request_id = str(uuid4())

        payload: Mapping[str, Any] = {
            "origin": {"lat": origin.lat, "lon": origin.lon},
            "destination": {"lat": destination.lat, "lon": destination.lon},
            "depart_at": depart_at.isoformat(),
            "preference": preference,
        }

        self.result_repository.put_pending(request_id=request_id, payload=payload)
        # Include request_id in the SQS message for the worker.
        self.queue_service.publish_request({"request_id": request_id, **dict(payload)})

        return request_id

    def get(self, *, request_id: str) -> Mapping[str, Any] | None:
        return self.result_repository.get(request_id=request_id)
