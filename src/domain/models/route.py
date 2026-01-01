from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .geo import GeoPoint
from .stop import Stop


class TravelMode(str, Enum):
    WALK = "walk"
    BUS = "bus"


@dataclass(frozen=True, slots=True)
class TransitLine:
    """Public transit line metadata (subset of GTFS routes.txt)."""

    route_id: str | None = None
    short_name: str | None = None
    long_name: str | None = None
    color: str | None = None  # hex without '#', per GTFS
    text_color: str | None = None  # hex without '#', per GTFS


@dataclass(frozen=True, slots=True)
class RouteLeg:
    mode: TravelMode
    origin: GeoPoint
    destination: GeoPoint
    distance_m: float | None = None
    duration_s: float | None = None
    stops: tuple[Stop, ...] = ()
    path: tuple[GeoPoint, ...] = ()
    line: TransitLine | None = None
    trip_id: str | None = None


@dataclass(frozen=True, slots=True)
class Route:
    origin: GeoPoint
    destination: GeoPoint
    legs: tuple[RouteLeg, ...] = field(default_factory=tuple)

    @property
    def total_distance_m(self) -> float | None:
        distances = [leg.distance_m for leg in self.legs]
        if any(d is None for d in distances):
            return None
        return float(sum(d for d in distances if d is not None))

    @property
    def total_duration_s(self) -> float | None:
        durations = [leg.duration_s for leg in self.legs]
        if any(d is None for d in durations):
            return None
        return float(sum(d for d in durations if d is not None))
