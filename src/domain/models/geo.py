from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GeoPoint:
    lat: float
    lon: float

    def __post_init__(self) -> None:
        if not (-90.0 <= self.lat <= 90.0):
            raise ValueError(f"Invalid latitude: {self.lat}")
        if not (-180.0 <= self.lon <= 180.0):
            raise ValueError(f"Invalid longitude: {self.lon}")
