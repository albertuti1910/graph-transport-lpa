from __future__ import annotations

import math

from src.domain.models import GeoPoint


def haversine_distance_m(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance in meters."""

    r = 6371000.0
    lat1 = math.radians(a.lat)
    lon1 = math.radians(a.lon)
    lat2 = math.radians(b.lat)
    lon2 = math.radians(b.lon)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    s = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    )
    return 2.0 * r * math.asin(math.sqrt(s))
