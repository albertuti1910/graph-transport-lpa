from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from src.app.ports.output import IGtfsRepository, IRealtimeVehicleProvider
from src.domain.models.geo import GeoPoint
from src.domain.models.gtfs import GtfsRoute
from src.domain.models.realtime import RealtimeVehicle


@dataclass(slots=True)
class RealtimeViewService:
    """Supports the realtime map view.

    - Lists transit routes/lines from static GTFS.
    - Returns a representative shape polyline per route_id.
    - Returns realtime vehicles (if provider configured).
    """

    gtfs_repository: IGtfsRepository
    vehicle_provider: IRealtimeVehicleProvider | None = None

    def list_routes(self) -> tuple[GtfsRoute, ...]:
        feed = self.gtfs_repository.load_feed()
        routes = list(feed.routes_by_id.values())
        routes.sort(key=lambda r: (r.short_name or "", r.long_name or "", r.route_id))
        return tuple(routes)

    def route_shape(self, *, route_id: str) -> tuple[GeoPoint, ...]:
        feed = self.gtfs_repository.load_feed()

        # Find the most common shape_id among trips for this route.
        shape_counts: Counter[str] = Counter()
        for trip in feed.trips_by_id.values():
            if trip.route_id != route_id:
                continue
            if not trip.shape_id:
                continue
            if trip.shape_id not in feed.shapes_by_id:
                continue
            shape_counts[trip.shape_id] += 1

        if not shape_counts:
            return ()

        shape_id, _ = shape_counts.most_common(1)[0]
        return feed.shapes_by_id.get(shape_id, ())

    async def list_vehicles(
        self, *, route_ids: set[str] | None = None
    ) -> tuple[RealtimeVehicle, ...]:
        if self.vehicle_provider is None:
            return ()

        vehicles = await self.vehicle_provider.list_vehicles()
        if route_ids:
            vehicles = tuple(
                v for v in vehicles if v.route_id and v.route_id in route_ids
            )
        return vehicles
