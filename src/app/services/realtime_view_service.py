from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from src.app.ports.output import IGtfsRepository, IRealtimeVehicleProvider
from src.domain.algorithms.geo_utils import haversine_distance_m
from src.domain.models.geo import GeoPoint
from src.domain.models.gtfs import GtfsRoute
from src.domain.models.realtime import RealtimeVehicle


def _build_cumulative_distances_m(points: tuple[GeoPoint, ...]) -> tuple[float, ...]:
    if len(points) < 2:
        return (0.0,) * len(points)

    out: list[float] = [0.0]
    total = 0.0
    for i in range(1, len(points)):
        total += haversine_distance_m(points[i - 1], points[i])
        out.append(total)
    return tuple(out)


def _interpolate_along_polyline(
    points: tuple[GeoPoint, ...], cumulative_m: tuple[float, ...], distance_m: float
) -> GeoPoint:
    if not points:
        return GeoPoint(lat=0.0, lon=0.0)
    if len(points) == 1:
        return points[0]

    total_m = cumulative_m[-1] if cumulative_m else 0.0
    if total_m <= 0.0:
        return points[0]

    d = max(0.0, min(float(distance_m), float(total_m)))

    # Find segment containing d (linear scan is fine for demo scale).
    for i in range(1, len(points)):
        if cumulative_m[i] >= d:
            d0 = cumulative_m[i - 1]
            d1 = cumulative_m[i]
            denom = max(1e-9, d1 - d0)
            t = (d - d0) / denom
            p0 = points[i - 1]
            p1 = points[i]
            return GeoPoint(
                lat=p0.lat + (p1.lat - p0.lat) * t,
                lon=p0.lon + (p1.lon - p0.lon) * t,
            )

    return points[-1]


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

    def route_shapes(
        self, *, route_id: str, max_shapes: int = 2
    ) -> tuple[tuple[str, tuple[GeoPoint, ...]], ...]:
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

        chosen: list[tuple[str, tuple[GeoPoint, ...]]] = []
        for shape_id, _ in shape_counts.most_common(max_shapes):
            pts = feed.shapes_by_id.get(shape_id)
            if not pts or len(pts) < 2:
                continue
            chosen.append((shape_id, pts))

        return tuple(chosen)

    def route_stops(self, *, route_id: str) -> tuple[tuple[str, str, GeoPoint], ...]:
        """Return unique stops used by trips of a route.

        Ordering is not guaranteed; intended for map markers.
        """

        feed = self.gtfs_repository.load_feed()

        trip_ids: set[str] = set()
        for trip in feed.trips_by_id.values():
            if trip.route_id == route_id:
                trip_ids.add(trip.trip_id)

        if not trip_ids:
            return ()

        stop_ids: set[str] = set()
        for c in feed.connections:
            if c.trip_id not in trip_ids:
                continue
            stop_ids.add(c.dep_stop_id)
            stop_ids.add(c.arr_stop_id)

        stops: list[tuple[str, str, GeoPoint]] = []
        for sid in stop_ids:
            s = feed.stops_by_id.get(sid)
            if s is None:
                continue
            stops.append((s.id, s.name, s.location))

        stops.sort(key=lambda x: (x[1], x[0]))
        return tuple(stops)

    async def list_vehicles(
        self, *, route_ids: set[str] | None = None
    ) -> tuple[RealtimeVehicle, ...]:
        # 1) Prefer realtime provider if configured.
        if self.vehicle_provider is not None:
            vehicles = await self.vehicle_provider.list_vehicles()
            if route_ids:
                vehicles = tuple(
                    v for v in vehicles if v.route_id and v.route_id in route_ids
                )
            return vehicles

        # 2) Fallback: schedule-based "pseudo realtime" from GTFS connections.
        feed = self.gtfs_repository.load_feed()
        now = datetime.now()
        now_s = now.hour * 3600 + now.minute * 60 + now.second

        trip_route: dict[str, str | None] = {
            t.trip_id: t.route_id for t in feed.trips_by_id.values()
        }

        trip_shape_id: dict[str, str | None] = {
            t.trip_id: t.shape_id for t in feed.trips_by_id.values()
        }

        # Cache per-shape geometry for interpolation.
        shape_cache: dict[str, tuple[tuple[GeoPoint, ...], tuple[float, ...]]] = {}

        # Cache nearest vertex lookup: (shape_id, stop_id) -> index
        nearest_vertex_cache: dict[tuple[str, str], int] = {}

        def get_shape(
            shape_id: str,
        ) -> tuple[tuple[GeoPoint, ...], tuple[float, ...]] | None:
            cached = shape_cache.get(shape_id)
            if cached is not None:
                return cached

            pts = feed.shapes_by_id.get(shape_id)
            if not pts or len(pts) < 2:
                return None

            cum = _build_cumulative_distances_m(pts)
            shape_cache[shape_id] = (pts, cum)
            return shape_cache[shape_id]

        def nearest_vertex_index(shape_id: str, stop_id: str) -> int | None:
            key = (shape_id, stop_id)
            if key in nearest_vertex_cache:
                return nearest_vertex_cache[key]

            stop = feed.stops_by_id.get(stop_id)
            geom = get_shape(shape_id)
            if stop is None or geom is None:
                return None

            pts, _ = geom
            best_i = 0
            best_d = float("inf")
            for i, p in enumerate(pts):
                d = haversine_distance_m(stop.location, p)
                if d < best_d:
                    best_d = d
                    best_i = i

            nearest_vertex_cache[key] = best_i
            return best_i

        active_by_trip: dict[str, tuple[str, str, int, int]] = {}
        for c in feed.connections:
            if not (c.dep_time_s <= now_s <= c.arr_time_s):
                continue
            rid = trip_route.get(c.trip_id)
            if route_ids and (rid is None or rid not in route_ids):
                continue
            prev = active_by_trip.get(c.trip_id)
            if prev is None or c.dep_time_s >= prev[2]:
                active_by_trip[c.trip_id] = (
                    c.dep_stop_id,
                    c.arr_stop_id,
                    c.dep_time_s,
                    c.arr_time_s,
                )

        vehicles_out: list[RealtimeVehicle] = []
        for trip_id, (a_stop, b_stop, dep_s, arr_s) in active_by_trip.items():
            a = feed.stops_by_id.get(a_stop)
            b = feed.stops_by_id.get(b_stop)
            if a is None or b is None:
                continue

            denom = max(1, arr_s - dep_s)
            t = max(0.0, min(1.0, (now_s - dep_s) / denom))

            # Default: straight interpolation between stop coordinates.
            lat = a.location.lat + (b.location.lat - a.location.lat) * t
            lon = a.location.lon + (b.location.lon - a.location.lon) * t
            dist_m = haversine_distance_m(a.location, b.location)
            speed_mps = float(dist_m / denom) if denom > 0 else None

            # If this trip has a GTFS shape, interpolate along the polyline instead.
            shape_id = trip_shape_id.get(trip_id)
            if shape_id:
                geom = get_shape(shape_id)
                if geom is not None:
                    pts, cum = geom
                    ia = nearest_vertex_index(shape_id, a_stop)
                    ib = nearest_vertex_index(shape_id, b_stop)

                    # Only use shape interpolation if stop order is consistent along polyline.
                    if ia is not None and ib is not None and ia < ib:
                        da = cum[ia]
                        db = cum[ib]
                        seg_m = max(0.0, db - da)
                        d_now = da + seg_m * t
                        p = _interpolate_along_polyline(pts, cum, d_now)
                        lat = p.lat
                        lon = p.lon
                        speed_mps = float(seg_m / denom) if denom > 0 else None

            rid = trip_route.get(trip_id)
            vehicles_out.append(
                RealtimeVehicle(
                    vehicle_id=None,
                    trip_id=trip_id,
                    route_id=rid,
                    lat=float(lat),
                    lon=float(lon),
                    speed_mps=speed_mps,
                    timestamp=now,
                )
            )

        return tuple(vehicles_out)
