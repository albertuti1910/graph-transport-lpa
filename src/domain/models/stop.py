from __future__ import annotations

from dataclasses import dataclass

from .geo import GeoPoint


@dataclass(frozen=True, slots=True)
class Stop:
    id: str
    name: str
    location: GeoPoint
