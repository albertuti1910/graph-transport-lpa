from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from src.app.services.realtime_view_service import RealtimeViewService
from src.domain.models.geo import GeoPoint
from src.domain.models.gtfs import Connection, GtfsFeed, GtfsRoute, GtfsTrip
from src.domain.models.realtime import RealtimeVehicle
from src.domain.models.stop import Stop


@dataclass(slots=True)
class FakeGtfsRepository:
    feed: GtfsFeed

    def load_feed(self) -> GtfsFeed:
        return self.feed


@dataclass(slots=True)
class FakeVehicleProvider:
    vehicles: tuple[RealtimeVehicle, ...]

    async def list_vehicles(self) -> tuple[RealtimeVehicle, ...]:
        return self.vehicles


def test_list_routes_sorted() -> None:
    feed = GtfsFeed(
        stops_by_id={},
        connections=(),
        routes_by_id={
            "R2": GtfsRoute(route_id="R2", short_name="2"),
            "R1": GtfsRoute(route_id="R1", short_name="1"),
            "R0": GtfsRoute(route_id="R0", short_name=None, long_name="Z"),
        },
        trips_by_id={},
        shapes_by_id={},
    )
    svc = RealtimeViewService(gtfs_repository=FakeGtfsRepository(feed))
    routes = svc.list_routes()

    assert [r.route_id for r in routes] == ["R0", "R1", "R2"]


def test_route_shapes_picks_most_common_shapes() -> None:
    feed = GtfsFeed(
        stops_by_id={},
        connections=(),
        routes_by_id={"R1": GtfsRoute(route_id="R1")},
        trips_by_id={
            "T1": GtfsTrip(trip_id="T1", route_id="R1", shape_id="S1"),
            "T2": GtfsTrip(trip_id="T2", route_id="R1", shape_id="S1"),
            "T3": GtfsTrip(trip_id="T3", route_id="R1", shape_id="S2"),
        },
        shapes_by_id={
            "S1": (GeoPoint(lat=0.0, lon=0.0), GeoPoint(lat=0.0, lon=1.0)),
            "S2": (GeoPoint(lat=1.0, lon=0.0), GeoPoint(lat=1.0, lon=1.0)),
        },
    )

    svc = RealtimeViewService(gtfs_repository=FakeGtfsRepository(feed))
    shapes = svc.route_shapes(route_id="R1", max_shapes=1)

    assert shapes and shapes[0][0] == "S1"


def test_route_stops_unique_and_sorted() -> None:
    stop_a = Stop(id="A", name="Alpha", location=GeoPoint(lat=0.0, lon=0.0))
    stop_b = Stop(id="B", name="Beta", location=GeoPoint(lat=0.0, lon=1.0))

    feed = GtfsFeed(
        stops_by_id={"A": stop_a, "B": stop_b},
        connections=(
            Connection(
                dep_stop_id="A",
                arr_stop_id="B",
                dep_time_s=0,
                arr_time_s=10,
                trip_id="T1",
            ),
        ),
        routes_by_id={"R1": GtfsRoute(route_id="R1")},
        trips_by_id={"T1": GtfsTrip(trip_id="T1", route_id="R1")},
        shapes_by_id={},
    )

    svc = RealtimeViewService(gtfs_repository=FakeGtfsRepository(feed))
    stops = svc.route_stops(route_id="R1")

    assert stops == (("A", "Alpha", stop_a.location), ("B", "Beta", stop_b.location))


def test_list_vehicles_uses_provider_and_filters_by_route_id() -> None:
    vehicles = (
        RealtimeVehicle(
            vehicle_id="v1",
            trip_id="t1",
            route_id="R1",
            lat=0.0,
            lon=0.0,
        ),
        RealtimeVehicle(
            vehicle_id="v2",
            trip_id="t2",
            route_id="R2",
            lat=1.0,
            lon=1.0,
        ),
    )
    feed = GtfsFeed(
        stops_by_id={},
        connections=(),
        routes_by_id={},
        trips_by_id={},
        shapes_by_id={},
    )

    svc = RealtimeViewService(
        gtfs_repository=FakeGtfsRepository(feed),
        vehicle_provider=FakeVehicleProvider(vehicles),
    )

    out = asyncio.run(svc.list_vehicles(route_ids={"R2"}))
    assert len(out) == 1
    assert out[0].route_id == "R2"


def test_list_vehicles_fallback_generates_pseudo_realtime(monkeypatch) -> None:
    class _FakeDateTime(datetime):
        @classmethod
        def now(cls):
            return datetime(2026, 1, 8, 8, 0, 30)

    from src.app.services import realtime_view_service as rvs

    monkeypatch.setattr(rvs, "datetime", _FakeDateTime)

    stop_a = Stop(id="A", name="A", location=GeoPoint(lat=0.0, lon=0.0))
    stop_b = Stop(id="B", name="B", location=GeoPoint(lat=0.0, lon=0.02))

    dep_s = 8 * 3600
    arr_s = dep_s + 60

    feed = GtfsFeed(
        stops_by_id={"A": stop_a, "B": stop_b},
        connections=(
            Connection(
                dep_stop_id="A",
                arr_stop_id="B",
                dep_time_s=dep_s,
                arr_time_s=arr_s,
                trip_id="T1",
            ),
        ),
        routes_by_id={"R1": GtfsRoute(route_id="R1")},
        trips_by_id={"T1": GtfsTrip(trip_id="T1", route_id="R1", shape_id="S1")},
        shapes_by_id={
            "S1": (
                GeoPoint(lat=0.0, lon=0.0),
                GeoPoint(lat=0.0, lon=0.01),
                GeoPoint(lat=0.0, lon=0.02),
            )
        },
    )

    svc = RealtimeViewService(
        gtfs_repository=FakeGtfsRepository(feed), vehicle_provider=None
    )
    out = asyncio.run(svc.list_vehicles(route_ids={"R1"}))

    assert len(out) == 1
    v = out[0]
    assert v.trip_id == "T1"
    assert v.route_id == "R1"
    # Should be somewhere between stop A and stop B.
    assert 0.0 <= v.lon <= 0.02
    assert v.timestamp is not None
