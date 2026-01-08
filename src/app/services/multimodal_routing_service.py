from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Mapping

import networkx as nx

from src.app.ports.output import IGtfsRepository, IMapProvider, IQueueService
from src.domain.algorithms.csa import earliest_arrival, reconstruct_connections
from src.domain.algorithms.geo_utils import haversine_distance_m
from src.domain.exceptions import NoPathFound
from src.domain.models import GeoPoint, Route, RouteLeg, Stop, TransitLine, TravelMode

Preference = Literal["fastest", "least_walking"]


@dataclass(slots=True)
class MultimodalRoutingService:
    """Walk + transit (GTFS) routing service.

    - Walking is computed over an OSM street graph.
    - Transit is computed with a basic CSA over GTFS stop_times.
    """

    gtfs_repository: IGtfsRepository
    map_provider: IMapProvider
    queue_service: IQueueService | None = None

    # Tuning knobs (MVP defaults)
    walk_speed_mps: float = 1.4
    max_candidate_stops: int = 12
    candidate_radius_m: float = 1500.0
    street_graph_dist_m: int = 8000

    def calculate_route(
        self,
        *,
        origin: GeoPoint,
        destination: GeoPoint,
        depart_at: datetime,
        preference: Preference,
    ) -> Route:
        depart_at = depart_at or datetime.now()

        feed = self.gtfs_repository.load_feed()

        # 1) Build a street graph centered on midpoint.
        center = GeoPoint(
            lat=(origin.lat + destination.lat) / 2.0,
            lon=(origin.lon + destination.lon) / 2.0,
        )
        street_graph = self.map_provider.get_street_graph(
            center=center, dist_m=int(self.street_graph_dist_m)
        )

        origin_street = self._street_name_for_point(street_graph, origin)
        destination_street = self._street_name_for_point(street_graph, destination)

        try:
            # 2) Candidate stops for access/egress.
            origin_candidates = self._candidate_stops(feed.stops_by_id, origin)
            dest_candidates = self._candidate_stops(feed.stops_by_id, destination)

            if not origin_candidates or not dest_candidates:
                raise NoPathFound("No nearby stops found for origin/destination")

            # 3) Initial times = depart_at + walk_time (+ penalty if least_walking)
            depart_s = self._seconds_since_midnight(depart_at)
            walk_penalty_s_per_m = 0.0 if preference == "fastest" else 2.0

            initial: dict[str, int] = {}
            origin_walk: dict[str, tuple[float, float]] = {}
            for stop in origin_candidates:
                dist_m = self._walk_distance_m(street_graph, origin, stop.location)
                if dist_m is None:
                    continue
                dur_s = dist_m / self.walk_speed_mps
                penalty_s = dist_m * walk_penalty_s_per_m
                initial[stop.id] = int(depart_s + dur_s + penalty_s)
                origin_walk[stop.id] = (dist_m, dur_s)

            if not initial:
                raise NoPathFound("No walkable access to any nearby stop")

            # 4) Run CSA.
            result = earliest_arrival(feed, initial_time_s_by_stop=initial)

            # 5) Pick best destination stop (+ final walk).
            best: tuple[float, Stop, float, float] | None = (
                None  # (cost_s, stop, walk_m, walk_s)
            )
            for stop in dest_candidates:
                arr_s = result.arrival_time_s_by_stop.get(stop.id)
                if arr_s is None:
                    continue

                dist_m = self._walk_distance_m(street_graph, stop.location, destination)
                if dist_m is None:
                    continue

                dur_s = dist_m / self.walk_speed_mps
                penalty_s = dist_m * walk_penalty_s_per_m
                cost = float(arr_s + dur_s + penalty_s)

                if best is None or cost < best[0]:
                    best = (cost, stop, dist_m, dur_s)

            if best is None:
                raise NoPathFound("No feasible route to destination")

            _, dest_stop, dest_walk_m, dest_walk_s = best

            # 6) Reconstruct transit connections and endpoints.
            conns = reconstruct_connections(result, dest_stop_id=dest_stop.id)
            if not conns:
                raise NoPathFound("No transit segment found (check GTFS schedules)")

            origin_stop = feed.stops_by_id[conns[0].dep_stop_id]

            # 7) Build Route legs.
            legs: list[RouteLeg] = []

            o_walk_m, o_walk_s = origin_walk.get(origin_stop.id, (None, None))
            if o_walk_m is None or o_walk_s is None:
                # Should be present; if not, recompute.
                d = self._walk_distance_m(street_graph, origin, origin_stop.location)
                if d is None:
                    raise NoPathFound("No walk segment to the chosen origin stop")
                o_walk_m = d
                o_walk_s = d / self.walk_speed_mps

            walk1_depart = depart_at
            walk1_arrive = depart_at + timedelta(seconds=float(o_walk_s))

            legs.append(
                RouteLeg(
                    mode=TravelMode.WALK,
                    origin=origin,
                    destination=origin_stop.location,
                    origin_name=origin_street,
                    destination_name=origin_stop.name,
                    destination_stop_id=origin_stop.id,
                    depart_at=walk1_depart,
                    arrive_at=walk1_arrive,
                    distance_m=float(o_walk_m),
                    duration_s=float(o_walk_s),
                    stops=(),
                    path=self._walk_path_points(
                        street_graph, origin, origin_stop.location
                    ),
                )
            )

            # Transit: split into legs per trip_id (so transfers show as separate lines).
            groups: list[list[Any]] = []
            current: list[Any] = []
            for c in conns:
                if not current or current[-1].trip_id == c.trip_id:
                    current.append(c)
                else:
                    groups.append(current)
                    current = [c]
            if current:
                groups.append(current)

            for g in groups:
                trip_id = g[0].trip_id
                trip = feed.trips_by_id.get(trip_id)
                route = (
                    feed.routes_by_id.get(trip.route_id)
                    if trip and trip.route_id
                    else None
                )

                boarded_at = feed.stops_by_id[g[0].dep_stop_id].location
                alighted_at = feed.stops_by_id[g[-1].arr_stop_id].location

                boarded_stop = feed.stops_by_id.get(g[0].dep_stop_id)
                alighted_stop = feed.stops_by_id.get(g[-1].arr_stop_id)

                # Build stop sequence for this trip group.
                stop_ids: list[str] = [g[0].dep_stop_id]
                stop_ids.extend(c.arr_stop_id for c in g)
                stops_seq: list[Stop] = []
                seen: set[str] = set()
                for sid in stop_ids:
                    if sid in seen:
                        continue
                    s = feed.stops_by_id.get(sid)
                    if s is None:
                        continue
                    stops_seq.append(s)
                    seen.add(sid)

                # Geometry: prefer GTFS shape polyline if available; else use stop-to-stop polyline.
                path: tuple[GeoPoint, ...] = ()
                if trip and trip.shape_id:
                    shape_pts = feed.shapes_by_id.get(trip.shape_id)
                    if shape_pts and len(shape_pts) >= 2:
                        path = self._slice_polyline_between_points(
                            shape_pts, start=boarded_at, end=alighted_at
                        )
                if not path and len(stops_seq) >= 2:
                    path = tuple(s.location for s in stops_seq)
                if not path:
                    # Fallback: at least show a straight segment.
                    path = (boarded_at, alighted_at)

                bus_distance_m = self._polyline_distance_m(path)
                bus_duration_s = float(max(0, g[-1].arr_time_s - g[0].dep_time_s))

                bus_depart = self._service_datetime_from_seconds(
                    depart_at, int(g[0].dep_time_s)
                )
                bus_arrive = self._service_datetime_from_seconds(
                    depart_at, int(g[-1].arr_time_s)
                )

                line = TransitLine(
                    route_id=route.route_id
                    if route
                    else (trip.route_id if trip else None),
                    short_name=route.short_name if route else None,
                    long_name=route.long_name if route else None,
                    color=route.color if route else None,
                    text_color=route.text_color if route else None,
                )

                legs.append(
                    RouteLeg(
                        mode=TravelMode.BUS,
                        origin=boarded_at,
                        destination=alighted_at,
                        origin_name=boarded_stop.name if boarded_stop else None,
                        destination_name=alighted_stop.name if alighted_stop else None,
                        origin_stop_id=boarded_stop.id if boarded_stop else None,
                        destination_stop_id=alighted_stop.id if alighted_stop else None,
                        depart_at=bus_depart,
                        arrive_at=bus_arrive,
                        distance_m=float(bus_distance_m),
                        duration_s=float(bus_duration_s),
                        stops=tuple(stops_seq),
                        path=tuple(path),
                        line=line,
                        trip_id=trip_id,
                    )
                )

            last_arrive = None
            for leg in reversed(legs):
                if leg.arrive_at is not None:
                    last_arrive = leg.arrive_at
                    break

            walk2_depart = last_arrive
            if walk2_depart is None:
                # Fallback (shouldn't happen): assume departure at requested time.
                walk2_depart = depart_at
            walk2_arrive = walk2_depart + timedelta(seconds=float(dest_walk_s))

            legs.append(
                RouteLeg(
                    mode=TravelMode.WALK,
                    origin=dest_stop.location,
                    destination=destination,
                    origin_name=dest_stop.name,
                    destination_name=destination_street,
                    origin_stop_id=dest_stop.id,
                    depart_at=walk2_depart,
                    arrive_at=walk2_arrive,
                    distance_m=float(dest_walk_m),
                    duration_s=float(dest_walk_s),
                    stops=(),
                    path=self._walk_path_points(
                        street_graph, dest_stop.location, destination
                    ),
                )
            )

            return Route(origin=origin, destination=destination, legs=tuple(legs))
        except NoPathFound:
            # For UX: always provide at least a walking option.
            return self._walking_only_route(street_graph, origin, destination)

    def _walking_only_route(
        self, graph: Any, origin: GeoPoint, destination: GeoPoint
    ) -> Route:
        origin_street = self._street_name_for_point(graph, origin)
        destination_street = self._street_name_for_point(graph, destination)
        dist_m = self._walk_distance_m(graph, origin, destination)
        if dist_m is None:
            dist_m = haversine_distance_m(origin, destination)
        dur_s = float(dist_m) / float(self.walk_speed_mps)

        depart_at = datetime.now()
        arrive_at = depart_at + timedelta(seconds=float(dur_s))
        leg = RouteLeg(
            mode=TravelMode.WALK,
            origin=origin,
            destination=destination,
            origin_name=origin_street,
            destination_name=destination_street,
            depart_at=depart_at,
            arrive_at=arrive_at,
            distance_m=float(dist_m),
            duration_s=float(dur_s),
            stops=(),
            path=self._walk_path_points(graph, origin, destination),
        )
        return Route(origin=origin, destination=destination, legs=(leg,))

    def _service_datetime_from_seconds(self, base: datetime, seconds: int) -> datetime:
        """Convert GTFS 'seconds since midnight' into an absolute datetime.

        Supports times over 24h (e.g. 25:10) by rolling into the next day.
        We treat the provided base datetime as the service day.
        """

        day0 = base.replace(hour=0, minute=0, second=0, microsecond=0)
        return day0 + timedelta(seconds=int(seconds))

    def _street_name_for_point(self, graph: Any, point: GeoPoint) -> str | None:
        """Best-effort street name for a coordinate.

        We use the nearest OSM edge and read its 'name' attribute.
        If OSMnx is unavailable or the edge has no name, returns None.
        """

        try:
            import osmnx as ox

            u, v, k = ox.distance.nearest_edges(graph, X=point.lon, Y=point.lat)
            data = None
            if hasattr(graph, "get_edge_data"):
                try:
                    data = graph.get_edge_data(u, v, k)
                except TypeError:
                    # Some graph types ignore the key.
                    data = graph.get_edge_data(u, v)

            if not isinstance(data, dict):
                return None

            name = data.get("name")
            if isinstance(name, (list, tuple)) and name:
                name = name[0]
            if isinstance(name, str):
                name = name.strip()
                return name or None
            return None
        except Exception:
            return None

    def _polyline_distance_m(self, points: tuple[GeoPoint, ...]) -> float:
        if len(points) < 2:
            return 0.0
        total = 0.0
        for a, b in zip(points, points[1:]):
            total += float(haversine_distance_m(a, b))
        return float(total)

    def _slice_polyline_between_points(
        self, points: tuple[GeoPoint, ...], *, start: GeoPoint, end: GeoPoint
    ) -> tuple[GeoPoint, ...]:
        """Return only the polyline segment between start and end.

        We snap start/end to the nearest points on the shape and slice the list.
        Ensures returned polyline begins at start and ends at end.
        """

        if len(points) < 2:
            return (start, end)

        def nearest_index(target: GeoPoint) -> int:
            best_i = 0
            best_d = float("inf")
            for i, p in enumerate(points):
                d = float(haversine_distance_m(p, target))
                if d < best_d:
                    best_d = d
                    best_i = i
            return best_i

        i0 = nearest_index(start)
        i1 = nearest_index(end)
        if i0 == i1:
            return (start, end)

        if i0 < i1:
            seg = list(points[i0 : i1 + 1])
        else:
            seg = list(points[i1 : i0 + 1])
            seg.reverse()

        # Force exact endpoints for visual clarity.
        seg[0] = start
        seg[-1] = end
        if len(seg) < 2:
            return (start, end)
        return tuple(seg)

    def enqueue_route_request(
        self,
        *,
        origin: GeoPoint,
        destination: GeoPoint,
        depart_at: datetime,
        preference: Preference,
    ) -> str:
        if self.queue_service is None:
            raise RuntimeError("Queue service not configured")

        message: Mapping[str, Any] = {
            "origin": {"lat": origin.lat, "lon": origin.lon},
            "destination": {"lat": destination.lat, "lon": destination.lon},
            "depart_at": depart_at.isoformat(),
            "preference": preference,
        }
        return self.queue_service.publish_request(message)

    def _candidate_stops(
        self, stops_by_id: dict[str, Stop], point: GeoPoint
    ) -> list[Stop]:
        # Cheap geographic prefilter.
        scored: list[tuple[float, Stop]] = []
        for s in stops_by_id.values():
            d = haversine_distance_m(point, s.location)
            if d <= self.candidate_radius_m:
                scored.append((d, s))

        scored.sort(key=lambda x: x[0])
        return [s for _, s in scored[: self.max_candidate_stops]]

    def _seconds_since_midnight(self, dt: datetime) -> int:
        # Treat provided datetime as local service time.
        return dt.hour * 3600 + dt.minute * 60 + dt.second

    def _nearest_node(self, graph: Any, point: GeoPoint) -> Any:
        # Fast path: use OSMnx spatial index if available (much faster than scanning all nodes).
        try:
            import osmnx as ox

            return ox.distance.nearest_nodes(graph, X=point.lon, Y=point.lat)
        except Exception:
            pass

        best_node: Any | None = None
        best_d2 = float("inf")

        for node_id, data in self._iter_nodes(graph):
            x = data.get("x")
            y = data.get("y")
            if x is None or y is None:
                continue
            try:
                lon = float(x)
                lat = float(y)
            except (TypeError, ValueError):
                continue

            d_lat = lat - point.lat
            d_lon = lon - point.lon
            d2 = d_lat * d_lat + d_lon * d_lon
            if d2 < best_d2:
                best_d2 = d2
                best_node = node_id

        if best_node is None:
            raise NoPathFound(
                "Street graph contains no georeferenced nodes (missing x/y)"
            )
        return best_node

    def _iter_nodes(self, graph: Any):
        if hasattr(graph, "nodes"):
            return ((n, dict(graph.nodes[n])) for n in graph.nodes)
        raise RuntimeError("Unsupported graph type")

    def _walk_distance_m(self, graph: Any, a: GeoPoint, b: GeoPoint) -> float | None:
        try:
            a_node = self._nearest_node(graph, a)
            b_node = self._nearest_node(graph, b)

            length = nx.shortest_path_length(graph, a_node, b_node, weight="length")
            return float(length)
        except Exception:
            return None

    def _walk_path_points(
        self, graph: Any, a: GeoPoint, b: GeoPoint
    ) -> tuple[GeoPoint, ...]:
        """Return a polyline of the walking route as GeoPoints."""

        try:
            a_node = self._nearest_node(graph, a)
            b_node = self._nearest_node(graph, b)
            path_nodes = nx.shortest_path(graph, a_node, b_node, weight="length")
            pts: list[GeoPoint] = []
            for node_id in path_nodes:
                data = dict(graph.nodes[node_id])
                x = data.get("x")
                y = data.get("y")
                if x is None or y is None:
                    continue
                try:
                    lon = float(x)
                    lat = float(y)
                except (TypeError, ValueError):
                    continue
                pts.append(GeoPoint(lat=lat, lon=lon))

            if len(pts) >= 2:
                return tuple(pts)
        except Exception:
            pass

        return (a, b)
