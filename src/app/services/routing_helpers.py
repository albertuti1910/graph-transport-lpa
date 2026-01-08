from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import networkx as nx

from src.domain.algorithms.geo_utils import haversine_distance_m
from src.domain.exceptions import NoPathFound
from src.domain.models import GeoPoint, Stop


def service_datetime_from_seconds(base: datetime, seconds: int) -> datetime:
    """Convert GTFS 'seconds since midnight' into an absolute datetime.

    Supports times over 24h (e.g. 25:10) by rolling into the next day.
    The provided base datetime is treated as the service day.
    """

    day0 = base.replace(hour=0, minute=0, second=0, microsecond=0)
    return day0 + timedelta(seconds=int(seconds))


def seconds_since_midnight(dt: datetime) -> int:
    # Treat provided datetime as local service time.
    return dt.hour * 3600 + dt.minute * 60 + dt.second


def candidate_stops(
    stops_by_id: dict[str, Stop], *, point: GeoPoint, radius_m: float, max_count: int
) -> list[Stop]:
    scored: list[tuple[float, Stop]] = []
    for stop in stops_by_id.values():
        d = haversine_distance_m(point, stop.location)
        if d <= radius_m:
            scored.append((d, stop))

    scored.sort(key=lambda x: x[0])
    return [s for _, s in scored[:max_count]]


def street_name_for_point(graph: Any, point: GeoPoint) -> str | None:
    """Best-effort street name for a coordinate.

    Uses the nearest OSM edge and reads its 'name' attribute.
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


def polyline_distance_m(points: tuple[GeoPoint, ...]) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += float(haversine_distance_m(a, b))
    return float(total)


def slice_polyline_between_points(
    points: tuple[GeoPoint, ...], *, start: GeoPoint, end: GeoPoint
) -> tuple[GeoPoint, ...]:
    """Return only the polyline segment between start and end.

    Snap start/end to nearest points on the shape and slice the list.
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

    seg[0] = start
    seg[-1] = end
    if len(seg) < 2:
        return (start, end)
    return tuple(seg)


def iter_nodes(graph: Any):
    if hasattr(graph, "nodes"):
        return ((n, dict(graph.nodes[n])) for n in graph.nodes)
    raise RuntimeError("Unsupported graph type")


def nearest_node(graph: Any, point: GeoPoint) -> Any:
    # Fast path: use OSMnx spatial index if available.
    try:
        import osmnx as ox

        return ox.distance.nearest_nodes(graph, X=point.lon, Y=point.lat)
    except Exception:
        pass

    best_node: Any | None = None
    best_d2 = float("inf")

    for node_id, data in iter_nodes(graph):
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
        raise NoPathFound("Street graph contains no georeferenced nodes (missing x/y)")
    return best_node


def walk_distance_m(graph: Any, a: GeoPoint, b: GeoPoint) -> float | None:
    try:
        a_node = nearest_node(graph, a)
        b_node = nearest_node(graph, b)
        length = nx.shortest_path_length(graph, a_node, b_node, weight="length")
        return float(length)
    except Exception:
        return None


def walk_path_points(graph: Any, a: GeoPoint, b: GeoPoint) -> tuple[GeoPoint, ...]:
    """Return a polyline of the walking route as GeoPoints."""

    try:
        a_node = nearest_node(graph, a)
        b_node = nearest_node(graph, b)
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
