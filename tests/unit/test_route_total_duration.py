from __future__ import annotations

from datetime import datetime, timedelta

from src.domain.models import GeoPoint, Route, RouteLeg, TravelMode


def test_total_duration_includes_waiting_when_timestamps_present() -> None:
    o = GeoPoint(lat=0.0, lon=0.0)
    a = GeoPoint(lat=0.0, lon=0.0)
    b = GeoPoint(lat=0.0, lon=0.0)

    t0 = datetime(2026, 1, 2, 8, 0, 0)

    walk = RouteLeg(
        mode=TravelMode.WALK,
        origin=o,
        destination=a,
        depart_at=t0,
        arrive_at=t0 + timedelta(minutes=5),
        duration_s=5 * 60,
        distance_m=100.0,
    )

    # Wait 10 minutes, then 3 minutes of bus.
    bus_depart = t0 + timedelta(minutes=15)
    bus = RouteLeg(
        mode=TravelMode.BUS,
        origin=a,
        destination=b,
        depart_at=bus_depart,
        arrive_at=bus_depart + timedelta(minutes=3),
        duration_s=3 * 60,
        distance_m=1000.0,
    )

    r = Route(origin=o, destination=b, legs=(walk, bus))

    assert r.total_duration_s == 18 * 60


def test_total_duration_falls_back_to_sum_when_no_timestamps() -> None:
    o = GeoPoint(lat=0.0, lon=0.0)
    a = GeoPoint(lat=0.0, lon=0.0)

    r = Route(
        origin=o,
        destination=a,
        legs=(
            RouteLeg(mode=TravelMode.WALK, origin=o, destination=a, duration_s=60.0),
            RouteLeg(mode=TravelMode.WALK, origin=a, destination=o, duration_s=120.0),
        ),
    )

    assert r.total_duration_s == 180.0
