from __future__ import annotations

from dataclasses import dataclass

from src.domain.models import Stop
from src.domain.models.geo import GeoPoint


@dataclass(frozen=True, slots=True)
class Connection:
    """A single scheduled transit connection between two stops.

    Times are seconds since service day midnight (GTFS time semantics; may exceed 24h).
    """

    dep_stop_id: str
    arr_stop_id: str
    dep_time_s: int
    arr_time_s: int
    trip_id: str


@dataclass(frozen=True, slots=True)
class GtfsRoute:
    route_id: str
    short_name: str | None = None
    long_name: str | None = None
    color: str | None = None  # hex without '#'
    text_color: str | None = None  # hex without '#'


@dataclass(frozen=True, slots=True)
class GtfsTrip:
    trip_id: str
    route_id: str | None = None
    shape_id: str | None = None


@dataclass(frozen=True, slots=True)
class GtfsFeed:
    """In-memory representation of the subset of GTFS needed for routing."""

    stops_by_id: dict[str, Stop]
    connections: tuple[Connection, ...]
    routes_by_id: dict[str, GtfsRoute]
    trips_by_id: dict[str, GtfsTrip]
    shapes_by_id: dict[str, tuple[GeoPoint, ...]]
