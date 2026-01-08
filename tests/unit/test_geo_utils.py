from __future__ import annotations

from src.domain.algorithms.geo_utils import haversine_distance_m
from src.domain.models.geo import GeoPoint


def test_haversine_zero_for_identical_points() -> None:
    p = GeoPoint(lat=28.1, lon=-15.4)
    assert haversine_distance_m(p, p) == 0.0


def test_haversine_is_symmetric_and_reasonable_scale() -> None:
    # Rough sanity check: 1 degree of latitude is about 111km.
    a = GeoPoint(lat=0.0, lon=0.0)
    b = GeoPoint(lat=1.0, lon=0.0)

    d1 = haversine_distance_m(a, b)
    d2 = haversine_distance_m(b, a)

    assert abs(d1 - d2) < 1e-6
    assert 100_000.0 < d1 < 120_000.0
