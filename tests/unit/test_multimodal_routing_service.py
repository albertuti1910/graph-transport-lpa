from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import networkx as nx

from src.app.services.multimodal_routing_service import MultimodalRoutingService
from src.domain.models import GeoPoint, Stop
from src.domain.models.gtfs import Connection, GtfsFeed, GtfsRoute, GtfsTrip


@dataclass(slots=True)
class FakeGtfsRepository:
    feed: GtfsFeed

    def load_feed(self) -> GtfsFeed:
        return self.feed


@dataclass(slots=True)
class FakeMapProvider:
    graph: nx.Graph

    def get_street_graph(self, *, center: GeoPoint, dist_m: int):
        return self.graph


@dataclass(slots=True)
class FakeQueueService:
    published: list[dict]

    def publish_request(self, message):
        self.published.append(dict(message))
        return "req-123"


def _tiny_graph() -> nx.Graph:
    g = nx.Graph()
    # Nodes carry lon/lat in x/y.
    g.add_node(1, x=0.0, y=0.0)
    g.add_node(2, x=0.0, y=0.01)
    g.add_node(3, x=0.0, y=0.02)
    g.add_edge(1, 2, length=100.0)
    g.add_edge(2, 3, length=200.0)
    return g


def test_calculate_route_builds_walk_bus_walk_legs_and_timestamps() -> None:
    origin = GeoPoint(lat=0.0, lon=0.0)
    destination = GeoPoint(lat=0.02, lon=0.0)

    stop_a = Stop(id="A", name="Stop A", location=origin)
    stop_b = Stop(id="B", name="Stop B", location=destination)

    depart_at = datetime(2026, 1, 8, 8, 0, 0)
    depart_s = 8 * 3600

    connections = (
        Connection(
            dep_stop_id="A",
            arr_stop_id="B",
            dep_time_s=depart_s + 300,
            arr_time_s=depart_s + 900,
            trip_id="T1",
        ),
    )

    feed = GtfsFeed(
        stops_by_id={"A": stop_a, "B": stop_b},
        connections=connections,
        routes_by_id={"R1": GtfsRoute(route_id="R1", short_name="1")},
        trips_by_id={"T1": GtfsTrip(trip_id="T1", route_id="R1", shape_id="S1")},
        # Simple 3-point shape to exercise polyline slicing.
        shapes_by_id={
            "S1": (
                GeoPoint(lat=0.0, lon=0.0),
                GeoPoint(lat=0.01, lon=0.0),
                GeoPoint(lat=0.02, lon=0.0),
            )
        },
    )

    service = MultimodalRoutingService(
        gtfs_repository=FakeGtfsRepository(feed),
        map_provider=FakeMapProvider(_tiny_graph()),
    )

    route = service.calculate_route(
        origin=origin,
        destination=destination,
        depart_at=depart_at,
        preference="fastest",
    )

    assert len(route.legs) == 3
    assert route.legs[0].mode.value == "walk"
    assert route.legs[1].mode.value == "bus"
    assert route.legs[2].mode.value == "walk"

    # Bus timestamps come from service-day seconds.
    day_start = depart_at.replace(hour=0, minute=0, second=0, microsecond=0)
    assert route.legs[1].depart_at == day_start + timedelta(seconds=depart_s + 300)
    assert route.legs[1].arrive_at == day_start + timedelta(seconds=depart_s + 900)


def test_enqueue_route_request_requires_queue_service_and_publishes_when_present() -> (
    None
):
    origin = GeoPoint(lat=0.0, lon=0.0)
    destination = GeoPoint(lat=0.0, lon=0.01)

    feed = GtfsFeed(
        stops_by_id={},
        connections=(),
        routes_by_id={},
        trips_by_id={},
        shapes_by_id={},
    )
    service = MultimodalRoutingService(
        gtfs_repository=FakeGtfsRepository(feed),
        map_provider=FakeMapProvider(_tiny_graph()),
        queue_service=None,
    )

    try:
        service.enqueue_route_request(
            origin=origin,
            destination=destination,
            depart_at=datetime(2026, 1, 8, 8, 0, 0),
            preference="fastest",
        )
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass

    queue = FakeQueueService(published=[])
    service.queue_service = queue
    req_id = service.enqueue_route_request(
        origin=origin,
        destination=destination,
        depart_at=datetime(2026, 1, 8, 8, 0, 0),
        preference="least_walking",
    )

    assert req_id == "req-123"
    assert queue.published and queue.published[0]["preference"] == "least_walking"


def test_walking_only_fallback_when_no_stops_found() -> None:
    origin = GeoPoint(lat=0.0, lon=0.0)
    destination = GeoPoint(lat=0.02, lon=0.0)

    stop_far = Stop(id="X", name="Far", location=GeoPoint(lat=50.0, lon=50.0))
    feed = GtfsFeed(
        stops_by_id={"X": stop_far},
        connections=(),
        routes_by_id={},
        trips_by_id={},
        shapes_by_id={},
    )

    service = MultimodalRoutingService(
        gtfs_repository=FakeGtfsRepository(feed),
        map_provider=FakeMapProvider(_tiny_graph()),
        candidate_radius_m=1.0,
    )

    route = service.calculate_route(
        origin=origin,
        destination=destination,
        depart_at=datetime(2026, 1, 8, 8, 0, 0),
        preference="fastest",
    )

    assert len(route.legs) == 1
    assert route.legs[0].mode.value == "walk"


def test_service_datetime_from_seconds_rolls_over_24h() -> None:
    feed = GtfsFeed(
        stops_by_id={},
        connections=(),
        routes_by_id={},
        trips_by_id={},
        shapes_by_id={},
    )
    service = MultimodalRoutingService(
        gtfs_repository=FakeGtfsRepository(feed),
        map_provider=FakeMapProvider(_tiny_graph()),
    )

    base = datetime(2026, 1, 8, 8, 0, 0)
    dt = service._service_datetime_from_seconds(base, 25 * 3600 + 10)

    assert dt.date() == datetime(2026, 1, 9).date()
    assert dt.hour == 1
    assert dt.minute == 0
    assert dt.second == 10
