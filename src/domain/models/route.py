from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
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
    origin_name: str | None = None
    destination_name: str | None = None
    origin_stop_id: str | None = None
    destination_stop_id: str | None = None
    depart_at: datetime | None = None
    arrive_at: datetime | None = None
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
        # Preferred: if we have timestamps, compute wall-clock duration.
        # This naturally includes waiting time and transfers.
        if self.legs:
            first_depart = next(
                (leg.depart_at for leg in self.legs if leg.depart_at), None
            )
            last_arrive = next(
                (leg.arrive_at for leg in reversed(self.legs) if leg.arrive_at),
                None,
            )
            if first_depart and last_arrive:
                delta = (last_arrive - first_depart).total_seconds()
                return float(max(0.0, delta))

        # Fallback: sum of leg durations (does not include waiting).
        durations = [leg.duration_s for leg in self.legs]
        if any(d is None for d in durations):
            return None
        return float(sum(d for d in durations if d is not None))
