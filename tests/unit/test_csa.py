from __future__ import annotations

from src.domain.algorithms.csa import earliest_arrival, reconstruct_connections
from src.domain.models.geo import GeoPoint
from src.domain.models.gtfs import Connection, GtfsFeed
from src.domain.models.stop import Stop


def _feed_with_connections(connections: tuple[Connection, ...]) -> GtfsFeed:
    # CSA only needs .connections, but the feed object requires all fields.
    stops_by_id = {
        "A": Stop(id="A", name="Stop A", location=GeoPoint(lat=0.0, lon=0.0)),
        "B": Stop(id="B", name="Stop B", location=GeoPoint(lat=0.0, lon=1.0)),
        "C": Stop(id="C", name="Stop C", location=GeoPoint(lat=0.0, lon=2.0)),
    }
    return GtfsFeed(
        stops_by_id=stops_by_id,
        connections=connections,
        routes_by_id={},
        trips_by_id={},
        shapes_by_id={},
    )


def test_earliest_arrival_basic_relaxation_and_reconstruction() -> None:
    # A -> B -> C chain is feasible if we can catch the departures.
    connections = (
        Connection(
            dep_stop_id="A",
            arr_stop_id="B",
            dep_time_s=10,
            arr_time_s=20,
            trip_id="T1",
        ),
        Connection(
            dep_stop_id="B",
            arr_stop_id="C",
            dep_time_s=25,
            arr_time_s=40,
            trip_id="T1",
        ),
    )
    feed = _feed_with_connections(connections)

    result = earliest_arrival(feed, initial_time_s_by_stop={"A": 0})

    assert result.arrival_time_s_by_stop["B"] == 20
    assert result.arrival_time_s_by_stop["C"] == 40

    used = reconstruct_connections(result, dest_stop_id="C")
    assert used == list(connections)


def test_earliest_arrival_skips_unreachable_departures() -> None:
    # First connection is missed (initial arrival at A happens after dep_time).
    connections = (
        Connection(
            dep_stop_id="A",
            arr_stop_id="B",
            dep_time_s=10,
            arr_time_s=20,
            trip_id="T1",
        ),
        Connection(
            dep_stop_id="A",
            arr_stop_id="B",
            dep_time_s=50,
            arr_time_s=60,
            trip_id="T2",
        ),
    )
    feed = _feed_with_connections(connections)

    result = earliest_arrival(feed, initial_time_s_by_stop={"A": 15})

    # Only the later connection can be taken.
    assert result.arrival_time_s_by_stop["B"] == 60
    used = reconstruct_connections(result, dest_stop_id="B")
    assert [c.trip_id for c in used] == ["T2"]
